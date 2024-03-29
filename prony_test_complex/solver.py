import json
import time
import pickle

from pymongo.errors import DuplicateKeyError
from importlib import import_module
from collections import defaultdict
from functools import reduce
from datetime import datetime, timedelta
from .settings import client


class StepCache(object):

    def __init__(self, base):
        self.cur_step_key = None
        self.base = base
        self.cache = defaultdict(dict)

    def get(self, step, options):

        name = f"cache_{step['required_parameter']}"
        key = frozenset((x, options[x]) for x in step['cached'])

        if key in self.cache[name]:
            return self.cache[name][key]

        record = self.base[name].find_one({'set_key': dict(key)})
        if record:
            res = pickle.loads(record['value'])
            self.cache[name][key] = res
            return res

        self.cur_step_key = key, name
        return None

    def commit(self, value):
        if self.cur_step_key:
            key, name = self.cur_step_key
            try:
                self.base[name].insert_one(
                    {'set_key': dict(key), 'value': pickle.dumps(value)})
            except DuplicateKeyError:
                print('Duplicate key')

        self.cur_step_key = None


class Solver(object):

    prognosis_period = 20

    def __init__(self, solution):

        solution = json.loads(solution)
        self.solution = solution
        self.base = client[solution['base']]
        self.self_calculate_iterations = 0

        self.count_documents = self.base[self.solution['schedule']].count_documents({})

        self.parameters = {
            parameter: {x['_id']: x for x in client[solution['base']][collection].find({})}
            for parameter, collection in solution['steps_parameters'].items()
        }

        self.pipeline = [
            {**action, 'action': self.step_loader(*action['action'])}
            for action in solution['steps']
        ]
        self.cache = StepCache(self.base)
        self.last_prognosis = 0
        self.last_prognosis_time = time.time()

    @staticmethod
    def step_loader(m_path, class_name):
        return reduce(lambda a, x: getattr(a, x), class_name.split('.'), import_module(m_path))

    def reload(self):
        self.base[self.solution['schedule']].update_many(
            {'processed': None}, {'$set': {'processed': False}}
        )

    def prognosis(self, current_iter):

        if (current_iter - self.last_prognosis) < self.prognosis_period:
            return

        iteration_delta = current_iter - self.last_prognosis
        avg_time = (time.time() - self.last_prognosis_time) / iteration_delta

        d_time = int((self.count_documents - current_iter) * avg_time)
        t_end = (datetime.now() + timedelta(seconds=d_time)).strftime('%d %b %H:%M')

        print(f"решено: "
              f"{current_iter}/{self.count_documents}".ljust(20),
              f"самостоятельно: "
              f"{self.self_calculate_iterations}/{iteration_delta}".ljust(15),
              f"заврешится: {t_end:15}"
              f"среднее: {round(avg_time, 4):<10}"
              f"[{datetime.now().strftime('%d %b %H:%M')}]"
              )
        self.self_calculate_iterations = 0
        self.last_prognosis = current_iter
        self.last_prognosis_time = time.time()

    def step_pipeline(self, options):

        data = {**self.solution['parameters']}
        for step in self.pipeline:

            cached_value = None

            if 'cached' in step:
                cached_value = self.cache.get(step, options)

            if cached_value:
                data.update(cached_value)
                continue

            step_params = {'data': data}
            if 'required_parameter' in step:
                param_name = step['required_parameter']
                step_params['params'] = self.parameters[param_name][options[param_name]]

            res = step['action'].step(**step_params)
            data.update(res)

            if 'cached' in step:
                self.cache.commit(res)

        return {'_id': options['_id']}, {'$set': {'result': data['log'], 'processed': True}}

    def calculate(self):
        options = None
        print('start solution')
        try:
            collection = self.base[self.solution['schedule']]
            while True:
                options = collection.find_one_and_update(
                    {'processed': False}, {'$set': {'processed': None}})

                if options is None:
                    print('End Solution')
                    return

                self.base[self.solution['schedule']].update(*self.step_pipeline(options))
                self.self_calculate_iterations += 1
                self.prognosis(options['_id'])

        except KeyboardInterrupt:
            if options:
                self.base[self.solution['schedule']].update(
                    {'_id': options['_id']}, {'$set': {'processed': False}})
            print('stop')
