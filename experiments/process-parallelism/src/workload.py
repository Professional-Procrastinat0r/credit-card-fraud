"""Three distinct fraud analyses, preserving the benchmark numerical workload.

Stage boundaries contain file references, not runner-specific model objects.
Files are local/shared-host artifacts in this controlled deployment.
"""
from pathlib import Path
import hashlib
import json
import os
import pickle
import warnings

import numpy as np


def folder(name):
    result = Path(os.environ['FRAUD_ANALYSIS_ARTIFACTS']) / name
    result.mkdir(parents=True, exist_ok=True)
    return result


def save_arrays(name, **arrays):
    result = {}
    for key, value in arrays.items():
        path = folder(name) / (key + '.npy')
        np.save(path, value, allow_pickle=False)
        result[key] = str(path)
    return result


def array(record, key):
    return np.load(record[key], allow_pickle=False)


def digest(value):
    return hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()


def save_model(branch, model):
    path = folder(branch) / 'model.pkl'
    path.write_bytes(pickle.dumps(model, protocol=5))
    return str(path)


def perform(kind, operation, deps, arguments, dataset, context=None):
    import pandas as pd
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import StandardScaler
    from sklearn.ensemble import HistGradientBoostingClassifier, IsolationForest
    from sklearn.neural_network import MLPRegressor
    from sklearn.exceptions import ConvergenceWarning
    from sklearn.metrics import (average_precision_score, roc_auc_score,
                                 precision_score, recall_score, f1_score, confusion_matrix)
    from threadpoolctl import threadpool_limits

    # Bound native threads even if a library was imported before runner setup.
    with threadpool_limits(limits=1):
        if operation == 'load':
            if context is not None and getattr(context, 'inputs', None) and 'training' in context.inputs:
                with context.inputs['training'].open('rb') as stream:
                    frame = pd.read_csv(stream)
            else:
                source = context.data_paths['training'] if context is not None else dataset
                frame = pd.read_csv(source)
            y = frame['Class'].to_numpy(dtype=np.int64)
            columns = [c for c in frame if c not in ['Class', 'Time']]
            x = frame[columns].to_numpy(dtype=np.float64)
            if not np.isfinite(x).all() or set(np.unique(y)) != {0, 1}:
                raise ValueError('Expected finite binary-labelled numeric fraud data')
            ids = np.arange(len(y), dtype=np.int64)
            if arguments.get('max_rows'):
                ids, _ = train_test_split(ids, train_size=arguments['max_rows'], stratify=y, random_state=42)
                ids.sort()
                x, y = x[ids], y[ids]
            return {**save_arrays('raw', x=x, y=y, ids=ids), 'columns': columns}

        if operation == 'split':
            raw = deps[0]
            x, y, ids = (array(raw, k) for k in ['x', 'y', 'ids'])
            tr, rest = train_test_split(np.arange(len(y)), test_size=0.4, stratify=y, random_state=42)
            va, te = train_test_split(rest, test_size=0.5, stratify=y[rest], random_state=42)
            values = {}
            for label, selected in [('train', tr), ('validation', va), ('test', te)]:
                values.update(save_arrays('split',
                    **{label+'_x': x[selected], label+'_y': y[selected], label+'_ids': ids[selected]}))
            # Keys deliberately explicit for auditing split membership.
            return {**values, 'columns': raw['columns']}

        if operation == 'prepare_branch':
            source = deps[0]
            branch = arguments['branch']
            train = array(source, 'train_x')
            if branch == 'autoencoder':
                train = train[array(source, 'train_y') == 0]
                scaler = StandardScaler().fit(train)
                transform = lambda x: np.clip(scaler.transform(x), -8, 8)
                scaler_path = save_model('autoencoder-scaler', scaler)
            else:
                transform = lambda x: x
                scaler_path = None
            arrays = save_arrays(branch+'-features', train_x=transform(train),
                validation_x=transform(array(source, 'validation_x')),
                test_x=transform(array(source, 'test_x')))
            return {**source, **arrays, 'scaler': scaler_path, 'branch': branch}

        if operation == 'train':
            features = deps[0]
            branch = arguments['branch']
            x = array(features, 'train_x')
            if branch == 'supervised':
                model = HistGradientBoostingClassifier(max_iter=arguments['iterations'], max_leaf_nodes=31,
                    learning_rate=0.08, class_weight='balanced', early_stopping=False, random_state=42)
                model.fit(x, array(features, 'train_y'))
            elif branch == 'isolation':
                model = IsolationForest(n_estimators=arguments['trees'], max_samples=min(8192,len(x)),
                                        random_state=42, n_jobs=1, contamination='auto')
                model.fit(x)
            else:
                model = MLPRegressor(hidden_layer_sizes=(32, 8, 32), activation='relu',
                    solver='adam', batch_size=512, max_iter=arguments['epochs'],
                    shuffle=True, random_state=42, early_stopping=False, tol=0,
                    n_iter_no_change=arguments['epochs']+1)
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter('always', ConvergenceWarning)
                    model.fit(x, x)
                if any(not isinstance(w.message, ConvergenceWarning) for w in caught):
                    raise RuntimeError('Unexpected training warning: '+str(caught))
                if model.n_iter_ != arguments['epochs']:
                    raise AssertionError('Autoencoder did not execute the declared epoch budget')
            return {**features, 'model': save_model(branch, model), 'training_rows': len(x)}

        if operation == 'score':
            trained = deps[0]
            model = pickle.loads(Path(trained['model']).read_bytes())
            branch = trained['branch']
            scores = {}
            for label in ['validation','test']:
                x = array(trained, label+'_x')
                if branch == 'supervised': score = model.predict_proba(x)[:,1]
                elif branch == 'isolation': score = -model.score_samples(x)
                else: score = np.mean((model.predict(x)-x)**2, axis=1)
                if not np.isfinite(score).all(): raise ValueError('Nonfinite prediction')
                scores[label+'_scores'] = score
            return {**trained, **save_arrays(branch+'-scores', **scores)}

        if operation == 'compare':
            reports = {}
            for scored in deps:
                vy, ty = array(scored,'validation_y'), array(scored,'test_y')
                vs, ts = array(scored,'validation_scores'), array(scored,'test_scores')
                # A fixed validation-only false-positive budget; never tune on test labels.
                threshold = float(np.quantile(vs[vy == 0], 0.99))
                pred = ts > threshold
                reports[scored['branch']] = dict(
                    training_rows=scored['training_rows'], threshold=threshold,
                    average_precision=float(average_precision_score(ty, ts)),
                    roc_auc=float(roc_auc_score(ty, ts)),
                    precision=float(precision_score(ty,pred,zero_division=0)),
                    recall=float(recall_score(ty,pred,zero_division=0)),
                    f1=float(f1_score(ty,pred,zero_division=0)),
                    confusion_matrix=confusion_matrix(ty,pred).tolist(),
                    validation_score_sha256=digest(vs), test_score_sha256=digest(ts))
            first = deps[0]
            return dict(schema=1,workload='fraud-distinct-processes',models=reports,
                split={label:dict(rows=len(array(first,label+'_y')),
                       fraud=int(array(first,label+'_y').sum()),
                       row_id_sha256=digest(array(first,label+'_ids')))
                       for label in ['train','validation','test']}, features=first['columns'])

        if operation == 'publish':
            report = deps[0]
            out = folder('report')
            (out/'comparison.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
            lines = ['# Fraud model comparison','', '| Model | Average precision | ROC-AUC | Recall |',
                     '| --- | ---: | ---: | ---: |']
            for name, row in report['models'].items():
                lines.append(f"| {name} | {row['average_precision']:.5f} | {row['roc_auc']:.5f} | {row['recall']:.5f} |")
            (out/'comparison.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
            bars = ''.join(f'<text x="5" y="{30+i*45}">{name}</text><rect x="150" y="{15+i*45}" width="{row["average_precision"]*400:.2f}" height="25" fill="#227c9d"/>' for i,(name,row) in enumerate(report['models'].items()))
            (out/'average-precision.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="600" height="160">'+bars+'</svg>',encoding='utf-8')
            return report
    raise ValueError(operation)
