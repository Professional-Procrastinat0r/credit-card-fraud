"""Scientific safeguards independent of the execution wrappers."""
from pathlib import Path
import os
import pickle
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from sklearn.datasets import make_classification

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import workload as w


class ScienceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.env=patch.dict(os.environ,{'FRAUD_ANALYSIS_ARTIFACTS':str(self.root/'artifacts')})
        self.env.start();self.addCleanup(self.env.stop)
        x,y=make_classification(n_samples=3000,n_features=8,n_informative=5,weights=[.96,.04],random_state=17)
        frame=pd.DataFrame(x,columns=['V'+str(i) for i in range(8)])
        frame['Class']=y;frame['Time']=np.arange(len(y))
        self.path=self.root/'data.csv';frame.to_csv(self.path,index=False)
        raw=w.perform(None,'load',[],{},self.path)
        self.split=w.perform(None,'split',[raw],{},None)

    def test_split_disjoint_and_excludes_time(self):
        ids=[set(w.array(self.split,label+'_ids')) for label in ['train','validation','test']]
        self.assertEqual(len(set.union(*ids)),3000)
        self.assertTrue(all(not ids[i]&ids[j] for i in range(3) for j in range(i)))
        self.assertNotIn('Time',self.split['columns'])
        self.assertEqual([len(s) for s in ids],[1800,600,600])

    def test_autoencoder_scaler_uses_only_normal_training_rows(self):
        prepared=w.perform(None,'prepare_branch',[self.split],{'branch':'autoencoder'},None)
        scaler=pickle.loads(Path(prepared['scaler']).read_bytes())
        normal=w.array(self.split,'train_x')[w.array(self.split,'train_y')==0]
        np.testing.assert_allclose(scaler.mean_,normal.mean(axis=0))
        self.assertEqual(len(w.array(prepared,'train_x')),len(normal))
        self.assertEqual(len(w.array(prepared,'test_x')),600)

    def test_models_reload_and_test_labels_do_not_select_thresholds(self):
        scores=[]
        for branch,budget in [('supervised',{'iterations':3}),('isolation',{'trees':4}),('autoencoder',{'epochs':2})]:
            prepared=w.perform(None,'prepare_branch',[self.split],{'branch':branch},None)
            trained=w.perform(None,'train',[prepared],{'branch':branch,**budget},None)
            scored=w.perform(None,'score',[trained],{},None)
            self.assertEqual(len(w.array(scored,'test_scores')),600)
            scores.append(scored)
        before=w.perform(None,'compare',scores,{},None)
        original=w.array(self.split,'test_y')
        np.save(self.split['test_y'],1-original,allow_pickle=False)
        after=w.perform(None,'compare',scores,{},None)
        for branch in before['models']:
            self.assertEqual(before['models'][branch]['threshold'],after['models'][branch]['threshold'])
            self.assertEqual(before['models'][branch]['test_score_sha256'],after['models'][branch]['test_score_sha256'])


if __name__=='__main__': unittest.main()
