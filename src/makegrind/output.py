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

import datetime
import json

__all__ = ["dump_callgrind", "dump_chrome_tracing"]


def dump_callgrind(graph, fd):
    fd.write("# callgrind format\n")
    fd.write("version: 1\n")
    fd.write("creator: {}\n".format(graph.entry.creator))
    fd.write("cmd: {}\n".format(" ".join(graph.entry.argv)))
    fd.write("desc: Node: Targets\n")
    fd.write("positions: line\n")
    fd.write("event: Wt : Wall Time\n")
    fd.write("event: Rt : Recipe Time\n")
    fd.write("events: Wt Rt\n\n")
    for target, data in graph.targets.info.items():
        if data.file is None:
            continue

        fd.write("\nob={}\n".format(data.directory))
        fd.write("fl={}\n".format(data.file))
        fd.write("fn={}\n".format(data.target))
        cost = [
            str(data.line),
            str(round(data.elapsed / datetime.timedelta(microseconds=1))),
        ]
        if data.recipe:
            recipe = data.elapsed_recipe
            cost.append(
                str(round(data.elapsed_recipe / datetime.timedelta(microseconds=1)))
            )
        fd.write("{}\n".format(" ".join(cost)))

        for dep in data.successors.values():
            if dep.file is None:
                continue
            fd.write("cob={}\n".format(dep.directory))
            fd.write("cfi={}\n".format(dep.file))
            fd.write("cfn={}\n".format(dep.target))
            fd.write("calls=1 {}\n".format(dep.line))
            fd.write(
                "{} {}\n".format(
                    data.line,
                    round(dep.elapsed / datetime.timedelta(microseconds=1)),
                )
            )


def dump_chrome_tracing(graph, fd):
    data = []

    def process(node, seen=set()):
        if node.key not in seen:
            seen.add(node.key)

            categories = []
            if node.file is None:
                categories.append("file")
            else:
                categories.append("target")
                if node.recipe:
                    categories.append("recipe")

            data.append(
                {
                    "name": node.target,
                    "ph": "B",
                    "cat": ",".join(categories),
                    "ts": round(node.start.timestamp() * 1000000),
                    "pid": node.pid,
                }
            )

            for child in node.successors.values():
                process(child)

            data.append(
                {
                    "name": node.target,
                    "ph": "E",
                    "ts": round(node.end.timestamp() * 1000000),
                    "pid": node.pid,
                }
            )

    for node in graph.entry.entry:
        process(graph.targets.info(node))

    json.dump(data, fd, indent=2)
