# Copyright 2021 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import copy
import datetime
from collections.abc import Mapping
from abc import ABCMeta, abstractmethod

import networkx as nx

from makegrind.util import find_path

import logging

logger = logging.getLogger(__name__)

__all__ = [
    "PercentEntity",
    "DurationEntity",
    "SummaryReport",
    "TopRecipesReport",
    "PathReport",
    "TopPathReport",
    "TopMakefileReport",
]


class ReportEntity:
    @classmethod
    def to_yaml(cls, dumper, data):
        return dumper.represent_str(cls.__str__(data))


class PercentEntity(ReportEntity):
    def __init__(self, numerator, denominator, precision=3):
        self.numerator = numerator
        self.denominator = denominator
        self.precision = precision

    def __str__(self):
        return "{} %".format(
            round(100 * self.numerator / self.denominator, self.precision)
        )


class DurationEntity(ReportEntity):
    def __init__(self, duration, precision=3):
        self.duration = duration
        self.precision = precision

    def __str__(self):
        return "{} s".format(round(self.duration.total_seconds(), self.precision))


class BuildReport(Mapping, metaclass=ABCMeta):
    def __init__(self, graph, precision=3):
        self.graph = graph
        self.data = None
        self.precision = 3

    def __getitem__(self, key):
        self.generate()
        return self.data.__getitem__(key)

    def __iter__(self):
        self.generate()
        return self.data.__iter__()

    def __len__(self):
        self.generate()
        return self.data.__len__()

    @property
    @abstractmethod
    def name(self):
        """Name of the report for reading"""
        return

    @property
    @abstractmethod
    def key(self):
        """Unique key identifying report type"""
        return

    @property
    def date(self):
        return self.graph.entry.start

    def round(self, value):
        return round(value, self.precision)

    def duration(self, value):
        return DurationEntity(value, self.precision)

    def percent(self, numerator, denominator):
        return PercentEntity(numerator, denominator, self.precision)

    @abstractmethod
    def __generate__(self):
        """Generate the report, note that yaml output respects the
        order that each element was added"""
        return

    def generate(self, force=False):
        """Run the report generation. Will use a cached report if available"""
        if force or self.data is None:
            self.data = self.__generate__(dict())

        return self.data

    def target_report(self, node, total=None, percent=lambda x: x.elapsed_recipe):
        if total is None:
            total = self.graph.elapsed

        if isinstance(node, str):
            node = self.graph.targets.info(node)

        return {
            "target": node.target,
            "total": self.duration(node.elapsed),
            "recipe": self.duration(node.elapsed_recipe),
            "percent": self.percent(percent(node), total),
            "dir": self.graph.relpath(node.directory),
            "pid": node.pid,
            "file": self.graph.relpath(node.path),
            "line": node.line,
            "recursive": node.recursive,
        }

    def children_report(self, node, key=None, max_children=None):
        if isinstance(node, str):
            node = self.graph.targets.info(node)

        total = node.elapsed

        if key is None:
            key = lambda d: -d.elapsed

        report = dict()

        children = sorted(node.successors.values(), key=key)
        report["count"] = len(children)
        if max_children is not None:
            children = children[:max_children]

        child_keys = lambda x: x[0] in ("target", "total", "percent")
        report["targets"] = list()
        for child in children:
            child_report = self.target_report(
                child, total=total, percent=lambda x: x.elapsed
            )
            report["targets"].append(dict(filter(child_keys, child_report.items())))

        return report

    @property
    def header(self):
        output = dict()
        output["key"] = self.key
        output["name"] = self.name
        output["date"] = self.date
        return output

    def __report__(self):
        """Return structured report data"""
        output = self.header
        output.update(copy.deepcopy(self.data))

        return output

    @property
    def report(self):
        self.generate()
        return self.__report__()

    @classmethod
    def to_yaml(cls, dumper, data):
        return dumper.represent_dict(data.report)

    def __str__(self):
        return str(self.report)


class SummaryReport(BuildReport):
    name = "Summary"
    key = "remake.summary.build"

    def __generate__(self, report):
        report["pid"] = self.graph.entry.pid
        report["total"] = self.duration(self.graph.elapsed)
        target_info = self.graph.targets.info
        report["recipe"] = self.duration(self.graph.elapsed_recipe)
        if self.graph.jobs:
            if self.graph.jobs is True:
                report["parallel"] = {"jobs": "unlimited"}
            else:
                report["parallel"] = {"jobs": self.graph.jobs}

            report["parallel"]["ratio"] = self.round(
                self.graph.elapsed_recipe / self.graph.elapsed
            )

        report["directory"] = self.graph.entry.directory
        report["submake"] = nx.number_of_nodes(self.graph)
        report["targets"] = nx.number_of_nodes(self.graph.targets)
        report["dependencies"] = nx.number_of_edges(self.graph.targets)
        report["entry"] = [
            self.graph.targets.nodes[x].name for x in self.graph.entry.entry
        ]
        return report


class TopRecipesReport(BuildReport):
    name = "Top Recipes"
    key = "remake.top.recipes"

    def __init__(self, graph, max_entries=10):
        super().__init__(graph)
        self.max_entries = max_entries

    def __generate__(self, report):
        report["total"] = self.duration(self.graph.elapsed)
        targets = sorted(
            (
                d
                for n, d in self.graph.targets.info.items()
                if not d.get("recursive", False)
            ),
            key=lambda d: d.elapsed_recipe,
            reverse=True,
        )

        total_recipe = sum((x.elapsed for x in targets), datetime.timedelta())
        report["recipe"] = self.duration(total_recipe)

        if self.graph.jobs:
            report["parallel"] = {
                "jobs": "unlimited" if self.graph.jobs is True else self.graph.jobs,
                "ratio": self.round(total_recipe / self.graph.elapsed),
            }

        nodes = list()
        for node in targets[: self.max_entries]:
            nodes.append(self.target_report(node))
        report["targets"] = nodes
        return report


class PathReport(BuildReport):
    name = "Path"
    key = "remake.summary.path"

    def __init__(self, graph, path, children=None):
        super().__init__(graph)
        self.path = path
        self.max_children = children

    def __generate__(self, report):
        report["length"] = len(self.path)
        total = self.graph.targets.info(self.path[0]).elapsed
        report["total"] = self.duration(total)
        report["targets"] = list()
        for node in self.path:
            target = self.target_report(node, total)
            child = self.children_report(node, max_children=self.max_children)
            if child["count"]:
                target["children"] = child
            report["targets"].append(target)

        return report


class TopPathReport(PathReport):
    name = "Top Path"
    key = "remake.top.path"

    def __init__(self, graph, **kwargs):
        path = find_path(graph)
        super().__init__(graph, path, **kwargs)


class TopMakefileReport(BuildReport):
    name = "Top Makefile Summary"
    key = "remake.top.makefile"

    def __init__(self, graph, max_entries=10, prefix=None):
        super().__init__(graph)
        self.max_entries = max_entries
        self.prefix = None if prefix is None else graph.relpath(prefix)

    def __generate__(self, report):
        dirs = dict()
        for build in self.graph.info.values():
            if self.prefix and not build.directory.startswith(self.prefix):
                continue

            if build.directory not in dirs:
                dirs[build.directory] = {
                    "keys": [build.key],
                    "elapsed": build.elapsed,
                }
            else:
                dirs[build.directory]["keys"].append(build.key)
                dirs[build.directory]["elapsed"] += build.elapsed
        paths = sorted(dirs.keys(), key=lambda x: -dirs[x]["elapsed"])
        report["directories"] = dict()
        for path in paths[: self.max_entries]:
            report["directories"][path] = {
                "elapsed": self.duration(dirs[path]["elapsed"]),
                "percent": self.percent(dirs[path]["elapsed"], self.graph.elapsed),
                "count": len(dirs[path]["keys"]),
            }

        return report


try:
    import yaml

    for name in __all__:
        cls = globals()[name]
        if hasattr(cls, "to_yaml"):
            yaml.add_representer(cls, cls.to_yaml)
    logging.debug("Reports registered with yaml")
except ImportError:
    logging.debug("Unable to load pyyaml, yaml formatting not supported")
