import tempfile
import numpy as np
from scipy.spatial.distance import cdist
from sklearn.base import TransformerMixin
from biom.util import biom_open
from skbio.stats.composition import clr
from skbio.stats import subsample_counts
from skbio.diversity.beta import unweighted_unifrac
from q2_anomaly_detection.utils import as_dense
from functools import partial
import pandas as pd
from unifrac import ssu


class AsDense(TransformerMixin):

    def fit(self, X, y=None):
        return self

    def transform(self, X, y=None):
        return as_dense(X)


class UniFrac(TransformerMixin):

    def __init__(self, tree_path):
        self.tree_path = tree_path
        self.table = None

    def fit(self, X, y=None):
        """

        X : biom.Table

        """
        self.table = X
        return self

    def transform(self, X):
        """

        X : biom.Table

        """
        # TODO one problem with this approach is that
        #  if any samples in X overlap self.table, the counts will
        #  be doubled
        merged_table = self.table.merge(X)
        with tempfile.NamedTemporaryFile() as f:
            with biom_open(f.name, 'w') as b:
                merged_table.to_hdf5(b, "merged")

            dm = ssu(f.name, self.tree_path,
                     unifrac_method='unweighted',
                     variance_adjust=False,
                     alpha=1.0,
                     bypass_tips=False,
                     threads=1,
                     )

        # get indices of test ID's
        X_idx = [dm.index(name) for name in X.ids('sample')]
        # get indices of table ID's
        ref_idx = [dm.index(name) for name in self.table.ids('sample')]

        # extract sub-distance matrix
        idxs = np.ix_(X_idx, ref_idx)
        sub_dm = dm.data[idxs]
        return sub_dm


class Rarefaction(TransformerMixin):

    def __init__(self, depth, replace=False):
        self.depth = depth
        self.replace = replace
        self.idx = None

    def fit(self, X, y=None):
        X, self.idx = self._find_nonzero_idx(X)
        return self

    def transform(self, X, y=None):
        """
        Caution: this will return different results for the same sample
        """
        if isinstance(X, pd.DataFrame):
            idx = np.array([True] * len(X.columns))
            idx[self.idx[:, 1]] = False
            X = X.loc[:, idx]
        else:
            X = np.delete(X, self.idx, axis=1)
        X = self._subsample(X)

        return X

    def _find_nonzero_idx(self, X):
        X = self._subsample(X)
        # remove columns with zero counts
        row_sums = X.sum(axis=0, keepdims=True)
        idx = np.argwhere(row_sums == 0)
        return X, idx

    def _subsample(self, X):
        X = X.astype(int)
        X_out = list()
        iter_var = X.values if isinstance(X, pd.DataFrame) else X
        for row in iter_var:
            new_X = subsample_counts(row, n=self.depth, replace=self.replace)
            X_out.append(new_X)
        X = np.vstack(X_out)
        return X


class CLR(TransformerMixin):

    def __init__(self, pseudocount=1):
        self.pseudocount = pseudocount

    def fit(self, X, y=None):
        return self

    def transform(self, X, y=None):
        return clr(X + self.pseudocount)
