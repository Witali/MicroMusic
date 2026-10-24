"""Automatic spectral-error minimization with a fixed intelligibility floor.

No weighted reward for higher STOI above the floor: accepted elites reduce the
same multiresolution spectral loss while retaining attained intelligibility.
Working annealing states may cross the floor; exported models may not.
"""
from joint_period import JointSearch
from period_book_search import BookSearch


class SpectralPolicy:
    def __init__(self, model, objective, *, stoi_floor=None, checkpoint=None, **kwargs):
        super().__init__(model, objective, checkpoint=None, **kwargs)
        floor = self.initial['stoi'] if stoi_floor is None else float(stoi_floor)
        if not 0 < floor <= self.initial['stoi']+1e-12:
            raise ValueError('Initial model does not meet the fixed intelligibility floor')
        self.config.pop('stoi_weight')
        self.config['objective'] = 'minimize_spectral_loss_under_fixed_stoi_floor-v1'
        self.config['stoi_floor'] = floor
        if checkpoint is not None:
            self.restore(checkpoint)

    def energy(self, score):
        return (score['loss'] + 100*max(0., self.config['stoi_floor']-score['stoi']) +
                100*max(0., score['log_spectral_error']-self.config['spectral_ceiling']) +
                100*max(0., score['peak']-self.config['max_peak']))


class SpectralFrameSearch(SpectralPolicy, JointSearch):
    pass


class SpectralBookSearch(SpectralPolicy, BookSearch):
    pass
