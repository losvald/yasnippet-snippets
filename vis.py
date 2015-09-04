#!/usr/bin/env python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import print_function

import argparse
import cgi
from collections import defaultdict
from collections import namedtuple
import contextlib
import errno
import json
from keyword import iskeyword
import os
import os.path
import re
import subprocess
import sys

__author__ = "Leo Osvald <leo.osvald@gmail.com>"

class Visualizer(object):
    def __init__(self, prefix_tree, hdr_key):
        self.prefix_tree = prefix_tree
        self.hdr_key = hdr_key

class DotVisualizer(Visualizer):
    def __init__(self, *args):
        super(DotVisualizer, self).__init__(*args)

    def __enter__(self):
        global args
        self.mode_colors = {} if args.no_mode_color else json.loads(
            "".join(args.mode_colors_file.readlines()))
        # print(self.colors, file=sys.stderr)
        self.out_basename = os.path.join(
            args.root_dir,
            args.mode[0] if len(args.mode) == 1 else "_all-modes"
        )
        self.out = (
            sys.stderr if args.dry_run else
            open(self.dot_path, "w")
        )
        self._print("digraph {\nrankdir=LR")
        self._print("node", self._stringify_attrs(
            shape="box",
        ))
        self._print("edge", self._stringify_attrs(fontname="courier"))
        self._gen(self.prefix_tree, [], [])
        self._print("}")

    def __call__(self):
        global args
        if self.out is not sys.stdout and self.out is not sys.stderr:
            self.out.close()
            fmt = os.path.splitext(self.img_path)[1][1:]
            cmd = ["dot", "-T" + fmt, "-o", self.img_path]
            with open(self.dot_path) as dot_inp:
                subprocess.check_call(cmd, stdin=dot_inp)
            if args.preview:
                cmd = os.getenv(
                    'YASNIPPET_VIS_PREVIEW',
                    "google-chrome --incognito"
                ) + " " + self.img_path
                subprocess.check_call(cmd, shell=True)

    def __exit__(self, exc_type, exc_value, traceback):
        os.remove(self.dot_path)
        if args.preview:
            os.remove(self.img_path)

    @property
    def dot_path(self):
        return self.out_basename + ".dot"

    @property
    def img_path(self):
        return self.out_basename + "." + args.dot_format.lower()

    def _print(self, *args, **kwargs):
        kwargs['file'] = self.out
        print(*args, **kwargs)

    def _stringify_attrs(self, **kwargs):
        return "[ " + ",".join(
            '%s=%s' % (
                k, "<" + "".join(v) + ">" if hasattr(v, '__iter__')
                else '"' + str(v) + '"')
            for k, v in kwargs.iteritems()
        ) + " ]"

    def _name_node(self, path):
        return "_" + "_".join(map(str, path))

    def _gen_node(self, node, path, prefix_str):
        name = self._name_node(path)
        attrs = {
            'URL': "http://www.google.com",
            'style': 'invisible',
            'tooltip': [cgi.escape(prefix_str)],
        }
        label = []
        if node.snippets:
            label.extend(['<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0">'])
        else:
            attrs['shape'] = "point"
        first = True
        for snippet in node.snippets:
            # attrs['URL'] = snippet.rel_path
            label.extend([
                '<TR>', '<TD HREF="%s">' % snippet.rel_path,
                '<FONT COLOR="%s">%s</FONT>' % (
                    self.mode_colors.get(snippet.major_mode, "black"),
                    cgi.escape(snippet.hdr['name']),
                )
            ])
            for hdr_prop in ('key', 'group'):
                if self.hdr_key != hdr_prop:
                    val = snippet.hdr.get(hdr_prop)
                    if val:
                        label.extend([
                            '<BR/><FONT POINT-SIZE="10" COLOR="gray">',
                            cgi.escape(val),
                            '</FONT>',
                        ])
            label.extend(['</TD>', '</TR>'])
            first = False
        if node.snippets:
            label.append('</TABLE>')
        # print(name, label, file=sys.stderr)
        attrs['label'] = label
        self._print(name, self._stringify_attrs(**attrs))

    def _gen_edge(self, tail, head, **attrs):
        self._print(tail, "->", head, self._stringify_attrs(**attrs))

    def _gen(self, node, path, prefix):
        global args
        tail, heads = self._name_node(path), []
        edges = node.sufs.keys()
        sort = args.sort == "all" or (args.sort == "root" and not path)
        if sort:
            edges.sort()
        for i, edge in enumerate(edges):
            child = node.sufs[edge]
            path.append(i)
            prefix.append(edge)
            self._gen_node(child, path, "".join(prefix))
            head = self._name_node(path)
            if heads and sort:
                self._gen_edge(heads[-1], head, style="invisible", dir="none")
            heads.append(head)
            edge_label = [cgi.escape(edge)]
            edge_attrs = {'label': edge_label, 'tooltip': edge_label}
            if len(path) == 1:
                root = self._name_node([i + len(node.sufs)])
                self._print(root, self._stringify_attrs(style="invisible"))
                self._gen_edge(root + ":e", head + ":w", **edge_attrs)
            else:
                self._gen_edge(tail, head, **edge_attrs)
            self._gen(child, path, prefix)
            path.pop()
            prefix.pop()
        if sort and heads:
            self._print("{ rank=same", " ".join(head for head in heads), "}")

class PrefixTree(object):
    def __init__(self):
        self.sufs = {}
        self.snippets = set()

    def put(self, key, snippet):
        p = self
        for c in key:
            p = p.sufs.setdefault(c, PrefixTree())
        p.snippets.add(snippet)

    def _compress(self, par_comp_edge=[]):
        for edge, subtree in self.sufs.items():  # copy since updating in-place
            comp_edge = [edge]
            subtree = subtree._compress(comp_edge)
            del self.sufs[edge]
            self.sufs["".join(comp_edge)] = subtree

        if len(self.sufs) == 1 and not self.snippets and par_comp_edge:
            sole_edge, sole_child = self.sufs.popitem()
            par_comp_edge.append(sole_edge)
            return sole_child

        return self

    def compress(self):
        return self._compress([])

    def _dfs(self, key_chunks, visitor, context):
        visitor(self, key_chunks, context)
        for edge, subtree in self.sufs.iteritems():
            key_chunks.append(edge)
            subtree._dfs(key_chunks, visitor, context)
            key_chunks.pop()

    def dfs(self, visitor, context):
        self._dfs([], visitor, context)

    def __str__(self):
        return "{0}@{1}".format(list(self.snippets), self.sufs)
    __repr__ = __str__

def relative_path(path):
    return os.path.relpath(path, args.root_dir)

def is_snippet(path):
    return (
        not path.startswith(".") and
        not path.startswith("#") and
        not path.endswith("~") and os.path.isfile(path)
    )

Snippet = namedtuple('Snippet', ['hdr', 'meta', 'body'])

class Snippet(object):
    _HEADER_END_RE = re.compile(r"^\s*#\s*--\s*$")
    _HEADER_META_RE = re.compile(r"^\s*#\s*-\*-\s+(.*)-\*-\s*$")
    _HEADER_KEY_VAL_RE = re.compile(r"^\s*#([^:]*):\s*(.*?)\s*$")

    def __init__(self, path):
        self.hdr = {}
        self.meta = {}
        body_lines = []
        hdr_parsed = False
        with open(path) as f:
            for line in f.readlines():
                if not hdr_parsed and self._HEADER_END_RE.match(line):
                    hdr_parsed = True
                    if args.body is None:
                        break

                if hdr_parsed:
                    body_lines.append(line)
                else:
                    line = line.strip()
                    m = self._HEADER_META_RE.match(line)
                    if m:
                        for k_v in m.group(1).split(";"):
                            k, _, v = map(
                                lambda s: s.strip(),
                                k_v.partition(":"))
                            self.meta[k] = v
                        continue

                    m = self._HEADER_KEY_VAL_RE.match(line)
                    if m:
                        k, v = map(lambda s: s.strip(), m.groups())
                        self.hdr[k] = v
            else:
                print(
                    "warning: no end of header in: " + relative_path(path),
                    file=sys.stderr)

        self.body = "".join(body_lines) if body_lines else None
        self.rel_path = os.path.relpath(path, args.root_dir)

    def matches(self, negatable_regexp_dict):
        for key, value in self._properties:
            neg_and_regexp = negatable_regexp_dict.get(key)
            if neg_and_regexp:
                negated, positive_regexp = neg_and_regexp
                if bool(positive_regexp.search(value)) == negated:
                    print("ignoring snippet: ", self.rel_path, file=sys.stderr)
                    return False
        return True

    @property
    def _properties(self):
        for key, value in self.hdr.iteritems():
            yield key, value
        for key, value in self.meta.iteritems():
            yield key, value
        yield 'path', self.rel_path
        yield 'body', self.body

    @property
    def major_mode(self):
        rel_path = self.rel_path
        major_mode_end = rel_path.find(os.sep)
        assert major_mode_end != -1
        return rel_path[:major_mode_end]

    def __hash__(self):
        return hash(self.rel_path)

    def __eq__(self, other):
        if not isinstance(other, Snippet):
            return False
        return self.rel_path == other.rel_path

    def __str__(self):
        return "{0} {1}".format(self.rel_path, self.hdr)

def compute_mode_deps(modes, deps=defaultdict(set), seen=set()):
    stack = modes[:]
    while stack:
        mode = stack.pop()
        if mode in seen:
            continue
        seen.add(mode)
        yas_parents_path = os.path.join(args.root_dir, mode, ".yas-parents")
        if not os.path.exists(yas_parents_path):
            continue
        with open(yas_parents_path) as f:
            dependent_modes = filter(
                lambda l: l,
                map(lambda l: l.strip(), f.readlines())
            )
            deps[mode] |= set(dependent_modes)
            stack.extend(dependent_modes)
            # print(mode, '->', dependent_modes, file=sys.stderr)
    return deps.copy()

def get_snippet_paths(modes):
    for dep_mode in modes:
        mode_path = os.path.join(args.root_dir, dep_mode)
        for dirpath, dirnames, fnames in os.walk(mode_path, followlinks=True):
            for fname in fnames:
                bad_prefix = fname.startswith(".") or fname.startswith("#")
                bad_suffix = fname.endswith("~")
                if bad_prefix or bad_suffix:
                    continue
                snippet_path = os.path.join(dirpath, fname)
                yield dep_mode, os.path.relpath(snippet_path, mode_path)

def match_mode_by_prefix(modes):
    def is_mode_dir(filename):
        return (
            not filename.startswith(".") and
            os.path.isdir(os.path.join(args.root_dir, filename))
        )
    modes = map(lambda mode: mode.rstrip(os.path.sep), modes)
    all_modes = filter(is_mode_dir, os.listdir(args.root_dir))
    return filter(
        lambda name: any(map(lambda prefix: name.startswith(prefix), modes)),
        all_modes)

def check_conflicts(hdr_key, tries):
    class Context(object):
        ok = True
    def report_conflicts(node, key_chunks, ctx):
        if len(node.snippets) > 1:
            ctx.ok = False
            non_unique = None
            for s in node.snippets:
                non_unique = non_unique or s.hdr.get(hdr_key)
            print("error:", hdr_key, "conflict:", non_unique,
                  file=sys.stderr)
            for s in node.snippets:
                print("@", s.rel_path, file=sys.stderr)
    ctx = Context()
    tries[hdr_key].dfs(report_conflicts, ctx)
    return ctx.ok

if __name__ == '__main__':
    global args
    prefix_tree_key_choices = ("key", "group", "name")

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root-dir",
        default=os.path.dirname(os.path.realpath(__file__)),
        help="Root directory of the YASNIPPET snippets",
    )
    parser.add_argument(
        "--no-parents", action='store_true', default=False,
        help="Do not include dependent modes as per .yas-parents",
    )
    parser.add_argument(
        "--no-compress", dest='compress', action='store_false',
        help="Do not compress prefix tree nodes without snippets")
    parser.add_argument(
        "--sort", choices=("all", "root", "none"), default="all",
        help="Which siblings to sort in the prefix tree",
    )
    parser.add_argument(
        "-k", "--key", choices=prefix_tree_key_choices, default="key",
        help="Key used for grouping snippets in the prefix tree",
    )
    parser.add_argument(
        "--name", metavar="REGEX",
        help="Filter snippets by name (prefix by (?~) to negate)")
    parser.add_argument(
        "--group", metavar="REGEX",
        help="Filter snippets by group (prefix by (?~) to negate)")
    parser.add_argument(
        "--path", metavar="REGEX",
        help="Filter snippets by relative path (prefix by (?~) to negate)")
    parser.add_argument(
        "--body", metavar="REGEX",
        help="Filter snippets by body (prefix by (?~) to negate)")
    parser.add_argument(
        "--mode-colors-file", nargs='?', type=argparse.FileType('r'),
        default=os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            ".mode-colors.json")
    )
    parser.add_argument("--no-mode-color", action='store_true')
    parser.add_argument(
        "--dot-format", default="svg",
        help="Output format of the visualizer (SVG by default)",
    )
    excl_group = parser.add_mutually_exclusive_group()
    excl_group.add_argument(
        "-p", "--preview", action='store_true',
        help=("Interactively preview in browser. The browser command is set" +
              " via the YASNIPPET_VIS_PREVIEW environmental variable."),
    )
    excl_group.add_argument(
        "-c", "--check-only", action='store_true',
        help="Do not generate any output, just check for conflicts",
    )
    parser.add_argument("-f", "--force", action='store_true')
    parser.add_argument("--dry-run", action='store_true')
    parser.add_argument(
        "mode", nargs='+',
        help="major mode; can be prefix if unique",
    )
    args = parser.parse_args()

    matching_modes = match_mode_by_prefix(args.mode)
    if not matching_modes:
        parser.error("no match for modes: " + ",".join(args.mode))
    args.mode = matching_modes

    deps = compute_mode_deps(args.mode)
    if args.no_parents:
        for mode in deps.keys():
            deps[mode].clear()

    def make_transitive(mode, seen):
        if mode not in seen:
            seen.add(mode)
            for mode_dep in deps[mode].copy():
                deps[mode] |= make_transitive(mode_dep, seen)
            deps[mode].add(mode)
        return deps[mode]
    modes = set()
    for mode in args.mode:
        dep_modes = make_transitive(mode, modes) - set([mode])
        if dep_modes:
            print(
                "dependent modes of {0}:".format(mode),
                ",".join(sorted(dep_modes)),
                file=sys.stderr)

    NEGATED_REGEX_PREFIX = "(?~)"
    regexps = dict((
        (key, (                 # map key to (<negated>, <positive_regex>)
            regexp_str.startswith(NEGATED_REGEX_PREFIX),
            re.compile(regexp_str.split(NEGATED_REGEX_PREFIX)[-1])))
        for (key, regexp_str) in filter(  # but only for specified regexes
                lambda key_regex: key_regex[1] is not None,
                ((key, getattr(args, key))
                 for key in ('name', 'group', 'path', 'body')))))

    trees = dict((hdr_key, PrefixTree()) for hdr_key in prefix_tree_key_choices)
    for mode, rel_path in get_snippet_paths(modes):
        snippet_path = os.path.join(args.root_dir, mode, rel_path)
        snippet = Snippet(snippet_path)
        if not snippet.matches(regexps):
            continue
        for hdr_key in trees:
            key = snippet.hdr.get(hdr_key)
            if key is not None:
                trees[hdr_key].put(key, snippet)
            elif hdr_key == 'key':
                print(
                    "warning: snippet without key:",
                    os.path.join(mode, rel_path),
                    file=sys.stderr)
    if args.compress:
        for hdr_key in trees.keys():  # copy
            trees[hdr_key] = trees[hdr_key].compress()

    # If several modes are specified, conflict checking is redundant
    # (i.e., only conflicts within dependency tree make sense)
    skip_check_conflicts = (len(matching_modes) > 1)
    if not skip_check_conflicts and not check_conflicts('name', trees):
        if not args.force:
            sys.exit(1)

    if not args.check_only:
        vis = DotVisualizer(trees[args.key], args.key)
        with vis:
            vis()
