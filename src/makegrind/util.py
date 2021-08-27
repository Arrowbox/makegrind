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
import logging

import makegrind.exceptions as mg_err

from networkx.algorithms import simple_paths as nxpath

logger = logging.getLogger(__name__)

__all__ = ["find_target", "find_path"]


def resolve_path(graph, path):
    """Translates a path to a relative path inside the graph.
    There are a few different possibilities with the path,
    1. It is an absolute path
    2. It is a relative path from the cwd
    3. It is a relative path from the root of the build"""

    abs_path = os.path.abspath(path)
    if graph.prefix == os.path.commonprefix([abs_path, graph.prefix]):
        path = abs_path
    else:
        path = os.path.join(graph.prefix, path)

    # Assume it is a relative path within the repo
    return graph.relpath(path)


def find_target(graph, target=None, makefile=None, pid=None):
    """Finds a node based on a target name, path to makefile, and pid. At least
    one must be set. Returns an iterable of nodes sorted by greatest elapsed time"""
    if target is None and makefile is None and pid is None:
        raise mg_err.TargetNotFoundError("No filtering criteria")

    logger.debug(
        "Finding target:'%s' in makefile:'%s' with pid:'%s'", target, makefile, pid
    )

    if makefile is not None:
        makefile = resolve_path(graph, makefile)

    def checker(node):
        data = node[1]
        if target is not None and data.name != target:
            return False
        if (
            makefile is not None
            and graph.relpath(data.path) != makefile
            and graph.relpath(data.directory) != makefile
        ):
            return False
        if pid is not None and data.pid != pid:
            return False
        return True

    nodes = sorted(
        filter(checker, graph.targets.nodes.data()), key=lambda x: x[1].elapsed
    )

    if not nodes:
        msg = ["No targets"]
        if target is not None:
            msg.append("named '{}'".format(target))
        if makefile is not None:
            msg.append("in file '{}'".format(makefile))
        if pid is not None:
            msg.append("with pid '{}'".format(pid))
        raise mg_err.TargetNotFoundError(" ".join(msg))

    targets = [x[0] for x in nodes]
    logger.debug("Found targets: %s", targets)
    return targets


def find_path(graph, targets=None):
    """Find a path through provided targets"""

    # We can skip finding paths and just find the heaviest one
    if not targets:
        entry = max(graph.entry.entry, key=lambda x: graph.targets.info(x).elapsed)
        return list(graph.targets.heaviest_path(entry))

    # Check each entry for a path to first target
    path = None
    for entry in graph.entry.entry:
        segments = nxpath.all_simple_paths(
            graph.targets, source=entry, target=targets[0]
        )
        for segment in segments:
            if (
                path is None
                or graph.targets.info(path[1]).elapsed
                < graph.targets.info(segment[1]).elapsed
            ):
                path = segment

    if path is None:
        raise mg_err.DepChainNotFoundError("Unable to find path to %s", targets[0])

    # Check for paths between each target provided
    for target in targets[1:]:
        next_segment = None
        segments = nxpath.all_simple_paths(
            graph.targets, source=path[-1], target=target
        )
        for segment in segments:
            if next_segment is None or graph.targets.info(
                next_segment[1]
            ).elapsed < graph.targets.info(segment[1]):
                next_segment = segment
        if next_segment is None:
            raise mg_err.DepChainNotFoundError(
                "Unable to find path from %s to %s", path[-1], target
            )
        path.extend(next_segment[1:])

    next_segment = list(graph.targets.heaviest_path(path[-1]))
    path.extend(next_segment[1:])
    return path
