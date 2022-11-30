# `makegrind`: The `Makefile` profiler

`makegrind` is a tool to analyze the output from [remake](https://github.com/rocky/remake)
to profile `make`-based build systems. When `remake` is used with `--profile=json`
the outputs can be parsed by `makegrind` using the [NetworkX](https://networkx.org)
library.

## Installation

The repository is compatible with setuptools. After cloning, run
`pip install path/to/makegrind` and the appropriate dependencies
should be installed.

## Usage

After installing `makegrind`, it can be run with
`makegrind --input path/to/build/directory <COMMAND>` where `<COMMAND>`
determines which report to generate. Each command provides a `--help` argument
to display possible options.

## Basic commands

* summary: Generates a short summary with aggregated statistics
* paths: Generates listing of dependency path taking the longest time
* dirs: Generates statistics over each directory
* recipes: Generates statistics on recipes taking the longest time
* callgrind: Generates an aggregate callgrind.out.target file
* chrome-tracing: Generates an aggregate chrome-tracing.out.targets file
  * You can view this either by using `chrome://tracing/` in your Chrome browser
    or visiting https://www.speedscope.app/.

## Reports

Reports are yaml-formatted for easier parsing by other tools. Each
report includes a few common keys.

* key: Can be used to identify the specific type of report
* name: An easily readable name for the report
* date: The initial start time of the build

## Disclaimer

This is not an officially supported Google product
