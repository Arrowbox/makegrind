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

import argparse
import json
import multiprocessing as mp
import os
import logging
import datetime

from abc import ABCMeta, abstractmethod

import networkx as nx
import networkx.algorithms.dag as dag

from makegrind.node import (
    TargetNode,
    BuildNode,
    BuildNodeInfoView,
    TargetNodeInfoView,
)
import makegrind.reports as reports

__all__ = ["TargetDiGraph", "BuildDiGraph"]

logger = logging.getLogger(__name__)


class MakeGrindDiGraph(nx.DiGraph, metaclass=ABCMeta):
    __cached__ = ["_reduced", "_entry"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.clear()

    def clear(self):
        """Clears cached attributes"""
        for x in self.__cached__:
            setattr(self, x, None)

    def nodekey(self, target):
        return self.node_attr_dict_factory.nodekey(target)

    @property
    @abstractmethod
    def node_info_view_factory(self):
        """Class that generates a node info view"""
        return

    @property
    def info(self):
        return self.node_info_view_factory(self)

    @property
    def reduced(self):
        if self._reduced is None:
            self._reduced = dag.transitive_reduction(self)

        return self._reduced

    @property
    def entry(self):
        if self._entry is None:
            for node in dag.topological_sort(self):
                if self.nodes[node].valid:
                    self._entry = node
                    break
            else:
                raise mg_exceptions.TargetNotFoundError("Unable to find entry point")

        return self.nodes[self._entry]

    def heaviest_child(self, node):
        return max(
            self.reduced.successors(node),
            key=lambda x: self.nodes[x].elapsed,
            default=None,
        )

    def heaviest_path(self, start=None):
        if start is None:
            start = self.entry.key

        while start:
            yield start
            start = self.heaviest_child(start)


class TargetDiGraph(MakeGrindDiGraph):
    node_attr_dict_factory = TargetNode
    node_info_view_factory = TargetNodeInfoView

    def add_target(self, target):
        key = self.nodekey(target)
        depends = target.pop("depends", list())
        if key not in self.nodes:
            self.add_node(key)
        self.nodes[key].update(target)

        for dep in [{"pid": target["pid"], "name": x} for x in depends]:
            self.add_edge(key, self.nodekey(dep))

    def add_nodes_from_build(self, build, targets):
        for target in targets:
            target["pid"] = build.pid
            target["directory"] = build.directory
            self.add_target(target)

    def add_parent_edges(self, build, parent):
        pkey = self.nodekey({"pid": parent["pid"], "name": parent["target"]})
        for entry in build.entry:
            self.add_edge(pkey, entry)
            self.nodes[pkey]["recursive"] = True

    @property
    def elapsed_recipe(self):
        return sum(
            (
                d.elapsed_recipe
                for d in self.info.values()
                if not d.get("recursive", False)
            ),
            datetime.timedelta(),
        )


class BuildDiGraph(MakeGrindDiGraph):
    node_attr_dict_factory = BuildNode
    node_info_view_factory = BuildNodeInfoView

    def __init__(self):
        super().__init__()
        self.targets = TargetDiGraph()
        self._entry = None

    def update(self, edges=None, nodes=None):
        super().update(edges, nodes)
        if hasattr(edges, "targets"):
            self.targets.update(edges.targets)

    def relpath(self, path):
        """Returns the path relative to the root directory of the graph"""
        if path is not None and path.startswith("/"):
            path = os.path.relpath(path, self.prefix)

        if path == ".":
            path = os.path.basename(self.prefix)

        return path

    @property
    def prefix(self):
        return self.entry.directory

    @staticmethod
    def node_name(pid, target):
        return "{}:{}".format(pid, target)

    @property
    def jobs(self):
        return self.entry.jobs

    @property
    def elapsed(self):
        return self.entry.elapsed

    @property
    def elapsed_recipe(self):
        return self.targets.elapsed_recipe

    def add_nodes_from_build(self, build):
        logger.debug("Adding build with pid: %s", build["pid"])
        targets = build.pop("targets", list())
        key = self.nodekey(build)

        self.add_node(key, **build)

        self.targets.add_nodes_from_build(self.nodes[key], targets)

        if "parent" in build:
            self.add_edge(self.nodekey(build["parent"]), key)
            self.targets.add_parent_edges(self.nodes[key], build["parent"])

    @classmethod
    def from_remake(cls, json_path):
        """Generate the graph from a json file output from remake"""

        logger.debug("Loading data from: %s", json_path)
        try:
            with open(json_path) as fd:
                return cls.from_json(fd.read())
        except Exception as e:
            logger.error("Error loading json from '%s'", json_path)
            raise e

    @classmethod
    def from_json(cls, json_str):
        """Generate the graph from a json string"""
        return cls.from_build(json.loads(json_str))

    @classmethod
    def from_build(cls, build):
        graph = cls()
        graph.add_nodes_from_build(build)
        return graph
