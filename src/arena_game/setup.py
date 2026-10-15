from glob import glob

from setuptools import find_packages, setup

package_name = 'arena_game'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        (
            'share/ament_index/resource_index/packages',
            ['resource/' + package_name]
        ),
        (
            'share/' + package_name,
            ['package.xml']
        ),
        (
            'share/' + package_name + '/launch',
            glob('launch/*.launch.py')
        ),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='gmucradl',
    maintainer_email='gmucradl@todo.todo',
    description='The star and decoy token game on the ROBOGAME arena',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'vision_node = arena_game.vision_node:main',
            'game_node = arena_game.game_node:main',
            'scoreboard_node = arena_game.scoreboard_node:main',
            'standalone = arena_game.standalone:main',
            'arena_check = arena_game.arena_check:main',
            'token_zones = arena_game.token_zones:main',
        ],
    },
)
