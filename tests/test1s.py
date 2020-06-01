import json
import numpy as np
from prony_test_complex import builder, steps, signals, scortcuts

BASE_NAME = 'db1s'
FILE_NAME = f'../solutions/{BASE_NAME}.json'


if input('Начать новый расчет? [Y/n]: ').lower() == 'y':

    test_builder = builder.Builder(
        BASE_NAME, {'range': [0.2, 0.5], 'fs': 20000, 'relative': True}
    )

    test_builder.add_steps([
        signals.OneSimpleTestSignal(),
        steps.CreateSignal(),
        steps.SNoise(np.linspace(0.0, 0.15, 31)),
        steps.SDecimation((1, 3, 5, 7)),
        steps.Filters([
            ('empty', scortcuts.empty_filter),
            ('wiener', scortcuts.s_win_filter),
        ]),
        steps.ComponentsCount(np.linspace(1, 100, 49)),
        steps.SComputing([
            ('ls', scortcuts.s_ls),
            ('mpm', scortcuts.s_mpm)
        ]),
        steps.Epsilon(),
        steps.Save()
    ])

    solution = test_builder.get_solution()

    with open(FILE_NAME, 'w') as f:
        json.dump(solution, f, indent=4)
