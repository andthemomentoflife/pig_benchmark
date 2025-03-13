# pig_benchmark
A Benchmark for python library migration

This repository is made up of existing benchmarks called "PyMigBench2.0" (https://github.com/ualberta-smr/PyMigBench), which is a benchmark for Python library migration.

The benchmark data is in /data directory. Each benchmark is composed of two python files and one json file. Json file contains basic information about migration. 

For example, 

```json
{
    "domain": "Filesystem", // domain of the migration
    "url": "https://github.com/studentenportal/web/commit/4842cff0", // url of the commit
    "bef_file": "1b.py", // before migration file
    "aft_file": "1a.py", // after migration file
    "libo": "unipath", // original library
    "libn": "pathlib", // new library
    "apio": [
        "Path",
        "ancestor",
        "child"
    ], // original API
    "apin": [
        "Path",
        "parents"
    ], // new API
    "api_imports": [
        "pathlib.Path"
    ], // imports of the new API
    "filepath": "config/settings.py", // file path
    "yaml": "unipath__pathlib__studentenportal@web__4842cff0.yaml" // yaml file
}
```