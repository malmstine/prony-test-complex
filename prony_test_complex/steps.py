import pickle
import numpy as np
from numpy.linalg import LinAlgError
from abc import abstractmethod, ABC


class Step(ABC):

    def __init__(self, cached=False):
        if cached:
            self.cached = cached

    @abstractmethod
    def step(self, data):
        pass


class RangeStep(ABC):

    def __init__(self, cached=False):
        if cached:
            self.cached = cached

    @abstractmethod
    def representative(self):
        pass

    @abstractmethod
    def step(self, data, params):
        pass

    @abstractmethod
    def get_parameters(self):
        pass


class EasyParametersMixin(ABC):

    @abstractmethod
    def representative(self):
        pass

    def __init__(self, parameters, **options):
        super().__init__(**options)
        self.parameters = parameters

    def get_parameters(self):
        return ({self.representative: x} for x in self.parameters)


class SetSize(EasyParametersMixin, RangeStep):

    representative = 'size'

    @classmethod
    def step(cls, data, params):
        return {'size': params['size']}


class Offset(EasyParametersMixin, RangeStep):

    representative = 'offset'

    @classmethod
    def step(cls, data, params):
        offset = params['offset'] * np.pi
        numbers = np.linspace(*map(lambda x: x + offset, data['range']), data['size'])
        source = data['start_signal'](numbers)
        return {'source': source}


class Noise(EasyParametersMixin, RangeStep):

    representative = 'sigma_k'

    @classmethod
    def step(cls, data, params):
        signal = data['source']
        noise = np.random.normal(0, params['sigma_k'] * max(signal), len(signal))
        res = signal + noise
        return {'signal': res}


class Filters(EasyParametersMixin, RangeStep):

    representative = 'filter'

    @classmethod
    def step(cls, data, params):
        result = pickle.loads(params['shortcut'])(data)
        if isinstance(result, dict):
            return result
        return {'signal': result}

    def get_parameters(self):
        return ({'filter': x[0], 'shortcut': pickle.dumps(x[1])} for x in self.parameters)


class Decimation(EasyParametersMixin, RangeStep):

    representative = 'step'

    @classmethod
    def step(cls, data, params):
        return {'signal': data['signal'][::params['step']], 'dec_step': params['step']}


class ComponentsCount(EasyParametersMixin, RangeStep):

    representative = 'p'

    @classmethod
    def step(cls, data, params):
        return {'p': params['p']}


class Computing(EasyParametersMixin, RangeStep):

    representative = 'method'

    @classmethod
    def step(cls, data, params):
        try:
            left, right = data['range']
            ts = np.abs(right - left) / len(data['signal']) / (2 * np.pi)
            signal = data['signal']

            p = data['p']
            if data.get('relative', False):
                p = data['p'] * len(signal) // 100

            result = pickle.loads(
                params['approximate'])(signal[np.newaxis].transpose(), p, ts)

        except (IOError, LinAlgError):
            result = None

        return {'success': bool(result), 'result': None if not result else {
            'params': result[0], 'restore': result[1]
        }}

    def get_parameters(self):
        return ({'method': x[0], 'approximate': pickle.dumps(x[1])} for x in self.parameters)


class Epsilon(Step):

    @classmethod
    def step(cls, data):

        if not data['success']:
            return data

        signal = data['result']['restore']
        diff = signal - data['source']
        return {'eps': np.sqrt(diff[np.newaxis].dot(diff)[0]) / len(diff)}


class Save(Step):

    @classmethod
    def step(cls, data):
        return {'log': None if not data['success'] else {
            'eps': data['eps'],
            'restore': data['result']['restore'].dumps(),
            'signal': data['signal'].dumps(),
            'params': list(map(lambda x: x.dumps(), data['result']['params'])),
        }}


class SimpleOffset(Step):

    @classmethod
    def step(cls, data):
        numbers = np.linspace(*data['range'], data['size'])
        source = data['start_signal'](numbers)
        return {'source': source}
