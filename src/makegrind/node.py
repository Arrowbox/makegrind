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

import os
import datetime
import logging

from collections.abc import MutableMapping, Mapping
from abc import ABCMeta, abstractmethod

import networkx.classes.reportviews as repv

logger = logging.getLogger(__name__)


class Node(MutableMapping, metaclass=ABCMeta):
    __cached__ = ["_elapsed", "_start", "_end"]

    __required__ = []

    def __init__(self):
        self.attrib = dict()
        self.clear()

    def clear(self):
        """Clears cached attributes"""
        for x in self.__cached__:
            setattr(self, x, None)

    @staticmethod
    @abstractmethod
    def nodekey(target):
        """Return the key generated from the node attributes"""
        return

    @property
    def key(self):
        """Returns node key used by DiGraph"""
        return self.nodekey(self.attrib)

    @property
    def start(self):
        if self._start is None:
            if self.attrib.get("start") is not None:
                self._start = datetime.datetime.fromtimestamp(self.attrib["start"])
            else:
                self._start = False

        return self._start

    @property
    def valid(self):
        for prop in self.__required__:
            if not hasattr(self, prop):
                return False
        return True

    @property
    def end(self):
        if self._end is None:
            if self.attrib.get("end") is not None:
                self._end = datetime.datetime.fromtimestamp(self.attrib["end"])
            else:
                self._end = False

        return self._end

    @property
    def elapsed(self):
        if self._elapsed is None:
            if not self.end or not self.start:
                self._elapsed = datetime.timedelta()
            else:
                self._elapsed = self.end - self.start

        return self._elapsed

    def __getattr__(self, name):
        if name in ["__getstate__", "__setstate__"]:
            # These are checked for pickling during multiprocessing
            raise AttributeError

        if name in self.attrib:
            return self.attrib[name]

        raise AttributeError("{} not in {}".format(name, self.__class__))

    def __getitem__(self, key):
        return self.attrib.__getitem__(key)

    def __setitem__(self, key, value):
        self.clear()
        return self.attrib.__setitem__(key, value)

    def __delitem__(self, key):
        self.clear()
        return self.__attrib.__delitem__(key)

    def __iter__(self):
        return self.attrib.__iter__()

    def __len__(self):
        return self.attrib.__len__()


class TargetNode(Node):
    __cached__ = Node.__cached__ + ["_recipe", "_elapsed_recipe"]
    __required__ = ["name", "pid"]

    def __init__(self):
        super().__init__()

    @staticmethod
    def nodekey(target):
        """Return the key generated from the node attributes"""
        return "{}:{}".format(target["pid"], target["name"])

    @property
    def target(self):
        return self.attrib["name"]

    @property
    def path(self):
        fname = self.attrib.get("file")
        fdir = self.attrib.get("directory")
        if fname and fdir:
            return os.path.join(fdir, fname)

    @property
    def recipe(self):
        if self._recipe is None:
            if self.attrib.get("recipe") is not None:
                self._recipe = datetime.datetime.fromtimestamp(self.attrib["recipe"])
            else:
                self._recipe = False

        return self._recipe

    @property
    def elapsed_recipe(self):
        if self._elapsed_recipe is None:
            if not self.end or not self.recipe:
                self._elapsed_recipe = datetime.timedelta()
            else:
                self._elapsed_recipe = self.end - self.recipe

        return self._elapsed_recipe


class NodeInfo(MutableMapping, metaclass=ABCMeta):
    def __init__(self, node, graph):
        super().__init__()
        self._node = node
        self._graph = graph

    @property
    def elapsed_recipe(self):
        if self._node.recursive is True:
            return datetime.timedelta()

        return self._node.elapsed_recipe

    @property
    def recursive(self):
        return self._node.get("recursive", False)

    def __getattr__(self, name):
        return getattr(self._node, name)

    def __getitem__(self, key):
        return self._node.__getitem__(key)

    def __setitem__(self, key, value):
        return self._node.__setitem__(key, value)

    def __delitem__(self, key):
        return self._node.__delitem__(key)

    def __iter__(self):
        return self._node.__iter__()

    def __len__(self):
        return self._node.__len__()


class TargetNodeInfo(NodeInfo):
    @property
    def target(self):
        if not self._node.target.startswith("/"):
            # Default back to node implementation
            raise AttributeError
        return self._graph.relpath(self._node.target)

    @property
    def file(self):
        if self._node.file is None:
            # Default back to node implementation
            raise AttributeError
        return self._graph.relpath(self.node.file)

    @property
    def successors(self):
        return self._graph.info(list(self._graph.successors(self._node.key)))


class TargetNodeInfoView(Mapping):
    def __init__(self, graph, nodes=None):
        self._graph = graph
        self._nodes = nodes

    def __call__(self, node):
        if isinstance(node, str):
            return TargetNodeInfo(self._graph.nodes[node], self._graph)

        return TargetNodeInfoView(self._graph, node)

    def __iter__(self):
        if self._nodes is None:
            return (x for x in self._graph.nodes)
        return (x for x in self._nodes)

    def __getitem__(self, n):
        if self._nodes is not None and n not in self._nodes:
            raise KeyError
        return TargetNodeInfo(self._graph.nodes[n], self._graph)

    def __len__(self):
        return len(list(self._nodes))


class BuildNode(Node):
    __required__ = ["pid", "directory"]

    def __init__(self):
        super().__init__()

    @staticmethod
    def nodekey(target):
        """Return the key generated from the node attributes"""
        return "{}".format(target["pid"])

    @property
    def entry(self):
        """Names of node entry points"""
        for ent in self.attrib["entry"]:
            yield TargetNode.nodekey({"pid": self.attrib["pid"], "name": ent})

    @property
    def jobs(self):
        if self.attrib["jobs"] == -1:
            # No parallelization
            return False
        elif self.attrib["jobs"] == 0:
            # Infinite number of jobs
            return True
        else:
            return self.attrib["jobs"]


class BuildNodeInfo(NodeInfo):
    @property
    def directory(self):
        return self._graph.relpath(self._node.directory)

    @property
    def recursive(self):
        """Time spent in recursive calls"""
        successors = self._graph.successors(self._node.key).data()
        submake = sum(data.elapsed for (node, data) in successors)


class BuildNodeInfoView(Mapping):
    def __init__(self, graph, nodes=None):
        self._graph = graph
        self._nodes = nodes

    def __call__(self, node):
        if isinstance(node, str):
            return BuildNodeInfo(self._graph.nodes[node], self._graph)

        return BuildNodeInfoView(self._graph, node)

    def __iter__(self):
        if self._nodes is None:
            return (x for x in self._graph.nodes)
        return (x for x in self._nodes)

    def __getitem__(self, n):
        if self._nodes is not None and n not in self._nodes:
            raise KeyError
        return BuildNodeInfo(self._graph.nodes[n], self._graph)

    def __len__(self):
        return len(list(self._nodes))
