from setuptools import setup
import versioneer

setup(
    name="wilmerlab-sjs",
    version=versioneer.get_version(),
    cmdclass=versioneer.get_cmdclass(),
    install_requires=[
        'click',
        'pyyaml',
        'redis',
        'rq',
    ],
    include_package_data=True,
    packages=['sjs'],
    entry_points={
        'console_scripts': [
            'sjs_status=sjs.scripts.sjs_status:sjs_status',
            'sjs_launch_workers=sjs.scripts.sjs_launch_workers:launch_workers',
        ]
    },
)
