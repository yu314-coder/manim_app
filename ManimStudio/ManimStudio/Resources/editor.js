/**
 * OfflinAi — Python completion, signature help, and hover provider for Monaco.
 *
 * Rich, client-side-only IntelliSense — no LSP round-trip required:
 *   - 35 Python keywords with snippets (for/while/def/class/try/…)
 *   - 50 Python builtins with snippets and signatures (print/range/open/…)
 *   - 500+ library symbols with rich docs: np/plt/math/random/os/sys/re/json/datetime/collections/itertools/functools/torch/transformers/huggingface_hub/manim/rich/bs4/click/yaml/jinja2/fsspec/webview/requests/scipy/sympy/tqdm
 *   - Signature help on `(` and `,` for every one
 *   - Hover docs on every symbol
 *   - Context detection: `self.`, `from X import`, alias resolution (np → numpy)
 *   - Progressive enhancement: unknown library members fall back to the Python daemon
 */

window.registerPythonProviders = function (monaco, editor) {
    const K    = monaco.languages.CompletionItemKind;
    const SNIP = monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet;

    // ─ Helpers ────────────────────────────────────────────────────────────────
    function mkRange(model, position) {
        const w = model.getWordUntilPosition(position);
        return {
            startLineNumber: position.lineNumber,
            endLineNumber:   position.lineNumber,
            startColumn:     w.startColumn,
            endColumn:       w.endColumn,
        };
    }

    function linePrefix(model, position) {
        const w = model.getWordUntilPosition(position);
        return model.getValueInRange({
            startLineNumber: position.lineNumber,
            startColumn: 1,
            endLineNumber: position.lineNumber,
            endColumn: w.startColumn,
        });
    }

    /// True only when the word being typed is the FIRST non-whitespace word
    /// on the current line. Used to gate statement-only completions (import,
    /// def, class, main snippet, docstring, …) so they never appear mid-
    /// expression like `x = foo(fr<cursor>` → don't suggest `from … import`.
    function isAtLineStart(model, position) {
        const w = model.getWordUntilPosition(position);
        const beforeWord = model.getValueInRange({
            startLineNumber: position.lineNumber, startColumn: 1,
            endLineNumber: position.lineNumber, endColumn: w.startColumn,
        });
        return /^\s*$/.test(beforeWord);
    }

    /// Statement-starter keywords (and snippets) that must only appear at the
    /// FIRST word of a line. Any of these mid-expression is a syntax error in
    /// Python (e.g. `x = foo(from …)` doesn't parse).
    const STATEMENT_KEYWORDS = new Set([
        'def', 'class', 'import', 'from', 'if', 'elif', 'else', 'for', 'while',
        'try', 'except', 'finally', 'with', 'return', 'yield', 'async', 'pass',
        'break', 'continue', 'raise', 'del', 'global', 'nonlocal', 'assert',
        // boilerplate snippets that ARE statements:
        'main', 'ifmain', 'docstring', '__init__', '__repr__', '__str__',
    ]);

    function parseImports(text) {
        const aliases = {};
        const wildcard = [];
        const fromSymbols = {};
        const lines = text.split('\n');
        const importRe = /^\s*import\s+([\w\.]+)(?:\s+as\s+(\w+))?/;
        const fromStarRe = /^\s*from\s+([\w\.]+)\s+import\s+\*/;
        const fromRe = /^\s*from\s+([\w\.]+)\s+import\s+(.+)$/;
        for (const line of lines) {
            let m;
            if ((m = line.match(fromStarRe))) {
                wildcard.push(m[1]);
            } else if ((m = line.match(fromRe))) {
                const mod = m[1];
                for (const piece of m[2].split(',')) {
                    const asMatch = piece.trim().match(/^(\w+)\s+as\s+(\w+)$/);
                    if (asMatch) {
                        fromSymbols[asMatch[2]] = mod;
                    } else {
                        const name = piece.trim().replace(/[()]/g, '');
                        if (name) fromSymbols[name] = mod;
                    }
                }
            } else if ((m = line.match(importRe))) {
                const modName = m[1];
                const alias = m[2] || modName.split('.')[0];
                aliases[alias] = modName;
            }
        }
        return { aliases, wildcard, fromSymbols };
    }

    const DEFAULT_ALIASES = {
        np: 'numpy',
        plt: 'matplotlib.pyplot',
        pd: 'pandas',
        nx: 'networkx',
        sp: 'scipy',
        sym: 'sympy',
        mpl: 'matplotlib',
        hf: 'huggingface_hub',
    };

    function resolveAlias(name, parsed) {
        return (parsed.aliases && parsed.aliases[name])
            || DEFAULT_ALIASES[name]
            || name;
    }

    // ─ Rich param object (same shape as Monaco expects) ──────────────────────
    const p = (label, doc) => ({ label, doc });

    // ═════════════════════════════════════════════════════════════════════════
    // KEYWORDS with snippets
    // ═════════════════════════════════════════════════════════════════════════
    function kwItems(range) {
        const kw = (label, snippet, doc) => ({
            label, kind: K.Keyword, range,
            insertText: snippet || label,
            insertTextRules: snippet ? SNIP : 0,
            documentation: doc ? { value: doc } : '',
            sortText: '1_' + label,
        });
        return [
            kw('def',      'def ${1:name}(${2:args}):\n\t"""${3:Docstring.}"""\n\t${0:pass}', 'Define a function.\n```python\ndef greet(name):\n    return f"Hello, {name}!"\n```'),
            kw('class',    'class ${1:Name}:\n\t"""${2:Docstring.}"""\n\n\tdef __init__(self${3:, args}):\n\t\t${0:pass}', 'Define a class.\n```python\nclass Point:\n    def __init__(self, x, y):\n        self.x, self.y = x, y\n```'),
            kw('import',   'import ${1:module}',                                                 'Import a module.'),
            kw('from',     'from ${1:module} import ${2:name}',                                 'Import a specific name from a module.'),
            kw('if',       'if ${1:condition}:\n\t${0:pass}',                                   'Conditional execution.'),
            kw('elif',     'elif ${1:condition}:\n\t${0:pass}',                                 'Else-if branch.'),
            kw('else',     'else:\n\t${0:pass}',                                                'Else branch.'),
            kw('for',      'for ${1:item} in ${2:iterable}:\n\t${0:pass}',                     'Iterate over an iterable.\n```python\nfor i in range(10):\n    print(i)\n```'),
            kw('while',    'while ${1:condition}:\n\t${0:pass}',                                'While loop.'),
            kw('try',      'try:\n\t${1:pass}\nexcept ${2:Exception} as ${3:e}:\n\t${0:pass}', 'Try/except/finally block.\n```python\ntry:\n    risky()\nexcept ValueError as e:\n    print(e)\n```'),
            kw('except',   'except ${1:Exception} as ${2:e}:\n\t${0:pass}',                    'Except clause.'),
            kw('finally',  'finally:\n\t${0:pass}',                                             'Finally clause.'),
            kw('with',     'with ${1:expr} as ${2:name}:\n\t${0:pass}',                         'Context manager.\n```python\nwith open("file") as f:\n    data = f.read()\n```'),
            kw('as'),
            kw('return',   'return ${0}',                                                        'Return a value from a function.'),
            kw('yield',    'yield ${0}',                                                         'Yield a value — turns a function into a generator.'),
            kw('lambda',   'lambda ${1:args}: ${0:expr}',                                        'Anonymous function.\n```python\nsquare = lambda x: x * x\n```'),
            kw('async',    'async def ${1:name}(${2:args}):\n\t${0:pass}',                      'Declare an async function.'),
            kw('await',    'await ${0}',                                                         'Await a coroutine.'),
            kw('pass',     null,                                                                 'No-op statement.'),
            kw('break',    null,                                                                 'Break out of the enclosing loop.'),
            kw('continue', null,                                                                 'Skip to the next loop iteration.'),
            kw('raise',    'raise ${1:Exception}(${0})',                                         'Raise an exception.'),
            kw('del',      'del ${0}',                                                           'Delete a name binding.'),
            kw('global',   'global ${0}',                                                        'Declare global name inside a function.'),
            kw('nonlocal', 'nonlocal ${0}',                                                      'Declare enclosing-scope name inside a nested function.'),
            kw('not'),
            kw('and'),
            kw('or'),
            kw('in'),
            kw('is'),
            kw('True'),
            kw('False'),
            kw('None'),
            kw('assert',   'assert ${1:condition}, ${2:"message"}',                              'Raise AssertionError if condition is falsy.'),
            // snippets
            kw('main',     'if __name__ == "__main__":\n\t${0:main()}',                          'Standard `if __name__ == "__main__":` guard.'),
            kw('ifmain',   'if __name__ == "__main__":\n\t${0:main()}',                          'Alias for `main` snippet.'),
            kw('docstring','"""${1:Summary.}\n\n${2:Description.}\n\nArgs:\n\t${3}\n\nReturns:\n\t${0}\n"""',           'Google-style docstring.'),
            kw('__init__', 'def __init__(self${1:, args}):\n\t${0:pass}',                        'Class constructor.'),
            kw('__repr__', 'def __repr__(self):\n\treturn f"${1:ClassName}({${2:}})"',            'Repr method.'),
            kw('__str__',  'def __str__(self):\n\treturn ${0:""}',                                'Str method.'),
        ];
    }

    // ═════════════════════════════════════════════════════════════════════════
    // PYTHON BUILTINS — full list with snippets and signatures
    // ═════════════════════════════════════════════════════════════════════════
    function builtinItems(range) {
        const fn = (label, snippet, doc) => ({
            label, kind: K.Function, range,
            insertText: snippet || (label + '(${0})'),
            insertTextRules: SNIP,
            documentation: doc ? { value: doc } : '',
            detail: 'builtin',
            sortText: '2_' + label,
        });
        return [
            fn('print',      'print(${0})',                              '**print(*values, sep=" ", end="\\n")** → None\n\nPrint values to stdout.\n```python\nprint("Hello", "world")\nprint(a, b, sep=", ", end="")\n```'),
            fn('len',        'len(${1:obj})',                             '**len(obj)** → int\n\nReturn the number of items in a container.\n```python\nlen([1, 2, 3])   # 3\nlen("hello")     # 5\n```'),
            fn('range',      'range(${1:stop})',                          '**range(stop)** or **range(start, stop[, step])** → range\n\nReturn an arithmetic progression.\n```python\nfor i in range(5): ...        # 0..4\nfor i in range(1, 10, 2): ... # 1,3,5,7,9\n```'),
            fn('list',       'list(${0})',                                '**list(iterable=())** → list\n\nBuild a list from an iterable.'),
            fn('dict',       'dict(${0})',                                '**dict(**kwargs)** or **dict(iterable)** → dict\n\nCreate a dictionary.'),
            fn('set',        'set(${0})',                                 '**set(iterable=())** → set\n\nCreate a set.'),
            fn('frozenset',  'frozenset(${0})',                           '**frozenset(iterable=())** → frozenset\n\nImmutable set.'),
            fn('tuple',      'tuple(${0})',                               '**tuple(iterable=())** → tuple\n\nCreate a tuple.'),
            fn('str',        'str(${1:obj})',                             '**str(obj)** → str\n\nConvert any object to its string form.'),
            fn('int',        'int(${1:obj})',                             '**int(x=0, base=10)** → int\n\nConvert to integer (optionally from base).'),
            fn('float',      'float(${1:obj})',                           '**float(x=0.0)** → float\n\nConvert to floating point.'),
            fn('complex',    'complex(${1:real}, ${2:imag})',             '**complex(real=0, imag=0)** → complex\n\nCreate a complex number.'),
            fn('bool',       'bool(${1:obj})',                            '**bool(x=False)** → bool\n\nConvert to boolean.'),
            fn('bytes',      'bytes(${1:obj})',                           '**bytes(source=b"")** → bytes\n\nCreate a bytes object.'),
            fn('bytearray',  'bytearray(${1:obj})',                       '**bytearray(source=b"")** → bytearray\n\nMutable bytes object.'),
            fn('type',       'type(${1:obj})',                            '**type(obj)** or **type(name, bases, dict)** → type\n\nGet type or construct a new class.'),
            fn('isinstance', 'isinstance(${1:obj}, ${2:type})',           '**isinstance(obj, classinfo)** → bool\n\nCheck type membership.'),
            fn('issubclass', 'issubclass(${1:cls}, ${2:parent})',         '**issubclass(cls, classinfo)** → bool\n\nCheck subclass relationship.'),
            fn('hasattr',    'hasattr(${1:obj}, ${2:"attr"})',            '**hasattr(obj, name)** → bool\n\nCheck if attribute exists.'),
            fn('getattr',    'getattr(${1:obj}, ${2:"attr"})',            '**getattr(obj, name[, default])** → Any\n\nGet attribute value.'),
            fn('setattr',    'setattr(${1:obj}, ${2:"attr"}, ${3:val})',  '**setattr(obj, name, value)**\n\nSet attribute value.'),
            fn('delattr',    'delattr(${1:obj}, ${2:"attr"})',            '**delattr(obj, name)**\n\nDelete attribute.'),
            fn('vars',       'vars(${1:obj})',                            '**vars(obj=None)** → dict\n\nReturn obj.__dict__.'),
            fn('dir',        'dir(${1:obj})',                             '**dir(obj=None)** → list\n\nReturn names available in obj.'),
            fn('enumerate',  'enumerate(${1:iterable})',                  '**enumerate(iterable, start=0)** → Iterator[tuple]\n\nYield (index, value) pairs.\n```python\nfor i, v in enumerate([a, b, c]):\n    print(i, v)\n```'),
            fn('zip',        'zip(${1:iter1}, ${2:iter2})',               '**zip(*iterables, strict=False)** → Iterator[tuple]\n\nPair up items from iterables.'),
            fn('map',        'map(${1:func}, ${2:iterable})',             '**map(func, *iterables)** → Iterator\n\nApply func to each item.\n```python\nlist(map(str, [1,2,3]))  # ["1","2","3"]\n```'),
            fn('filter',     'filter(${1:func}, ${2:iterable})',          '**filter(func, iterable)** → Iterator\n\nKeep items where func(item) is truthy.'),
            fn('sorted',     'sorted(${1:iterable})',                     '**sorted(iterable, *, key=None, reverse=False)** → list\n\nReturn new sorted list.'),
            fn('reversed',   'reversed(${1:iterable})',                   '**reversed(seq)** → iterator\n\nReverse iterator.'),
            fn('sum',        'sum(${1:iterable})',                        '**sum(iterable, /, start=0)** → number\n\nSum of all elements.'),
            fn('min',        'min(${1:iterable})',                        '**min(iterable, *, key=None, default=MISSING)** → Any\n\nMinimum value.'),
            fn('max',        'max(${1:iterable})',                        '**max(iterable, *, key=None, default=MISSING)** → Any\n\nMaximum value.'),
            fn('abs',        'abs(${1:x})',                               '**abs(x)** → number\n\nAbsolute value.'),
            fn('round',      'round(${1:x}, ${2:ndigits})',               '**round(number, ndigits=None)** → number\n\nRound to n decimal places.'),
            fn('pow',        'pow(${1:base}, ${2:exp})',                  '**pow(base, exp, mod=None)** → number\n\nExponentiation.'),
            fn('divmod',     'divmod(${1:a}, ${2:b})',                    '**divmod(a, b)** → tuple\n\n(a // b, a % b).'),
            fn('open',       'open(${1:"file"}, ${2:"r"})',               '**open(file, mode="r", encoding=None, ...)** → file\n\nOpen a file. Modes: r/w/a/x + b/t + "+".'),
            fn('input',      'input(${1:"prompt: "})',                    '**input(prompt="")** → str\n\nRead a line from stdin.'),
            fn('super',      'super()',                                    '**super()** → proxy\n\nProxy for calling parent-class methods.'),
            fn('property',   'property(${1:fget})',                       '**property(fget=None, fset=None, fdel=None, doc=None)**\n\nProperty descriptor. Use as @property.'),
            fn('staticmethod','staticmethod(${0})',                       '**@staticmethod**\n\nMark a method as static (no self/cls).'),
            fn('classmethod', 'classmethod(${0})',                        '**@classmethod**\n\nMark a method as receiving cls instead of self.'),
            fn('all',        'all(${1:iterable})',                        '**all(iterable)** → bool\n\nTrue iff every element is truthy.'),
            fn('any',        'any(${1:iterable})',                        '**any(iterable)** → bool\n\nTrue iff any element is truthy.'),
            fn('iter',       'iter(${1:iterable})',                       '**iter(obj)** or **iter(callable, sentinel)** → iterator'),
            fn('next',       'next(${1:iterator})',                       '**next(iterator, default=MISSING)** → Any\n\nAdvance iterator.'),
            fn('hash',       'hash(${1:obj})',                            '**hash(obj)** → int'),
            fn('id',         'id(${1:obj})',                              '**id(obj)** → int\n\nUnique identity integer.'),
            fn('repr',       'repr(${1:obj})',                            '**repr(obj)** → str\n\nPrintable representation.'),
            fn('format',     'format(${1:value}, ${2:spec})',             '**format(value, format_spec="")** → str'),
            fn('callable',   'callable(${1:obj})',                        '**callable(obj)** → bool\n\nCan obj be called?'),
            fn('chr',        'chr(${1:i})',                               '**chr(i)** → str\n\nUnicode codepoint → character.'),
            fn('ord',        'ord(${1:c})',                               '**ord(c)** → int\n\nCharacter → Unicode codepoint.'),
            fn('hex',        'hex(${1:x})',                               '**hex(x)** → str\n\n"0x…" hex representation.'),
            fn('oct',        'oct(${1:x})',                               '**oct(x)** → str\n\n"0o…" octal representation.'),
            fn('bin',        'bin(${1:x})',                               '**bin(x)** → str\n\n"0b…" binary representation.'),
            fn('slice',      'slice(${1:start}, ${2:stop}, ${3:step})',   '**slice(start, stop, step=None)** → slice'),
            fn('eval',       'eval(${1:"expr"})',                         '**eval(source, globals=None, locals=None)** → Any ⚠ Unsafe with untrusted input.'),
            fn('exec',       'exec(${1:"stmts"})',                        '**exec(source, globals=None, locals=None)** ⚠ Unsafe with untrusted input.'),
            fn('compile',    'compile(${1:source}, ${2:filename}, ${3:mode})','**compile(source, filename, mode, flags=0)** → code'),
            fn('globals',    'globals()',                                 '**globals()** → dict'),
            fn('locals',     'locals()',                                  '**locals()** → dict'),
            fn('help',       'help(${1:obj})',                            '**help(obj=None)**\n\nInteractive help.'),
        ];
    }

    // ═════════════════════════════════════════════════════════════════════════
    // IMPORT SHORTCUTS
    // ═════════════════════════════════════════════════════════════════════════
    function importSnippets(range) {
        const s = (label, snippet, doc) => ({
            label, kind: K.Snippet, range,
            insertText: snippet,
            insertTextRules: SNIP,
            documentation: doc ? { value: doc } : '',
            detail: 'import',
            sortText: '0_' + label,
        });
        return [
            s('import numpy',      'import numpy as np\n',                   'Import NumPy as np.'),
            s('import matplotlib', 'import matplotlib.pyplot as plt\n',      'Import matplotlib.pyplot as plt.'),
            s('import sympy',      'import sympy as sym\n',                  'Import SymPy as sym.'),
            s('import scipy',      'from scipy import ${1:optimize, stats}\n','Import from SciPy.'),
            s('import pandas',     'import pandas as pd\n',                  'Import pandas as pd.'),
            s('import sklearn',    'from sklearn import ${1:datasets}\n',    'Import from scikit-learn.'),
            s('import networkx',   'import networkx as nx\n',                'Import NetworkX as nx.'),
            s('import manim',      'from manim import *\n',                  'Import all of Manim.'),
            s('import requests',   'import requests\n',                      'Import requests HTTP client.'),
            s('import json',       'import json\n',                          'Import JSON.'),
            s('import os',         'import os\n',                            'Import OS utilities.'),
            s('import sys',        'import sys\n',                           'Import system-specific parameters.'),
            s('import math',       'import math\n',                          'Import math module.'),
            s('import random',     'import random\n',                        'Import random module.'),
            s('import re',         'import re\n',                            'Import regular expressions.'),
            s('import datetime',   'from datetime import datetime, timedelta\n','Import datetime.'),
            s('import collections','from collections import ${1:defaultdict, Counter}\n','Import collections classes.'),
            s('import itertools',  'import itertools\n',                     'Import itertools.'),
            s('import functools',  'import functools\n',                     'Import functools.'),
            s('import torch',      'import torch\nimport torch.nn as nn\n',  'Import PyTorch + nn module.'),
            s('import transformers','from transformers import AutoModel, AutoTokenizer\n','Import HuggingFace transformers.'),
            s('import huggingface_hub','from huggingface_hub import snapshot_download\n','Import HuggingFace Hub helpers.'),
            s('import tokenizers', 'from tokenizers import Tokenizer\n',     'Import HuggingFace tokenizers.'),
            s('import safetensors','from safetensors.torch import load_file, save_file\n','Import safetensors (torch flavor).'),
            s('import av',         'import av\n',                            'Import PyAV (FFmpeg bindings).'),
            s('import bs4',        'from bs4 import BeautifulSoup\n',        'Import BeautifulSoup HTML parser.'),
            s('import click',      'import click\n',                         'Import click CLI framework.'),
            s('import rich',       'from rich import print\nfrom rich.console import Console\nfrom rich.markdown import Markdown\n','Import rich terminal formatting.'),
            s('import jsonschema', 'import jsonschema\n',                    'Import JSON Schema validator.'),
            s('import yaml',       'import yaml\n',                          'Import PyYAML.'),
            s('import jinja2',     'from jinja2 import Environment, Template\n','Import Jinja2 template engine.'),
            s('import fsspec',     'import fsspec\n',                        'Import fsspec filesystem abstraction.'),
            s('import certifi',    'import certifi\n',                       'Import certifi (CA bundle).'),
            s('import pywebview',  'import webview\n',                       'Import pywebview (routes to in-app preview pane).'),
            s('import latex',      'import offlinai_latex\n',                'Import CodeBench LaTeX bridge (Busytex).'),
            s('import ai',         'import offlinai_ai\n',                   'Import CodeBench local-AI bridge.'),
            s('import plotly',     'import plotly.express as px\nimport plotly.graph_objects as go\n','Import Plotly Express + graph_objects.'),
            s('import PIL',        'from PIL import Image\n',                'Import Pillow Image.'),
            s('import urllib3',    'import urllib3\n',                       'Import urllib3.'),
            s('import packaging',  'from packaging.version import Version\n','Import packaging version helpers.'),
        ];
    }

    // ═════════════════════════════════════════════════════════════════════════
    // LIBRARY SYMBOL DATABASES — hardcoded, rich, instant
    // ═════════════════════════════════════════════════════════════════════════
    // Shape: { aliasOrModule: { name: { sig, doc, kind? } } }
    // `kind` optional — defaults to Function. Use 'const' for constants, 'class' for classes.

    const LIB_SYMBOLS = {
        // ── NumPy (np.*) ────────────────────────────────────────────────────
        numpy: {
            // Array creation
            array:      { sig: 'array(object, dtype=None, copy=True)', doc: 'Create an ndarray.\n```python\nnp.array([1, 2, 3])\nnp.array([[1, 2], [3, 4]])\n```' },
            zeros:      { sig: 'zeros(shape, dtype=float)',            doc: 'Array of zeros.\n```python\nnp.zeros(5)        # [0. 0. 0. 0. 0.]\nnp.zeros((2, 3))   # 2×3 matrix of zeros\n```' },
            ones:       { sig: 'ones(shape, dtype=float)',             doc: 'Array of ones.' },
            empty:      { sig: 'empty(shape, dtype=float)',            doc: 'Uninitialized array (garbage contents).' },
            full:       { sig: 'full(shape, fill_value, dtype=None)',  doc: 'Array filled with `fill_value`.' },
            eye:        { sig: 'eye(N, M=None, k=0, dtype=float)',     doc: 'Identity matrix (1 on k-th diagonal).' },
            identity:   { sig: 'identity(n, dtype=float)',             doc: 'Square identity matrix.' },
            arange:     { sig: 'arange(start, stop=None, step=1, dtype=None)', doc: 'Evenly spaced values.\n```python\nnp.arange(10)        # 0..9\nnp.arange(1, 5, 0.5) # [1., 1.5, 2., 2.5, 3., 3.5, 4., 4.5]\n```' },
            linspace:   { sig: 'linspace(start, stop, num=50, endpoint=True)', doc: 'num evenly-spaced samples from start to stop.' },
            logspace:   { sig: 'logspace(start, stop, num=50, endpoint=True, base=10.0)', doc: 'Log-spaced samples.' },
            meshgrid:   { sig: 'meshgrid(*xi, indexing="xy")',         doc: 'Coordinate matrices from coordinate vectors.' },
            mgrid:      { sig: 'mgrid[slice1, slice2, ...]',           doc: 'Dense multi-dimensional meshgrid.', kind: 'const' },
            ogrid:      { sig: 'ogrid[slice1, slice2, ...]',           doc: 'Open multi-dimensional meshgrid.', kind: 'const' },
            // Random
            random:     { sig: 'random.random(size=None)',             doc: 'Random float in [0, 1).', kind: 'mod' },
            // Reshape / manip
            reshape:    { sig: 'reshape(a, newshape, order="C")',      doc: 'Give array a new shape (no data copy if possible).' },
            ravel:      { sig: 'ravel(a, order="C")',                  doc: 'Flatten to 1-D.' },
            flatten:    { sig: 'ndarray.flatten(order="C")',           doc: 'Flatten to 1-D (always copies).' },
            transpose:  { sig: 'transpose(a, axes=None)',              doc: 'Permute dimensions.' },
            concatenate:{ sig: 'concatenate((a1, a2, ...), axis=0)',   doc: 'Join arrays along existing axis.' },
            stack:      { sig: 'stack(arrays, axis=0)',                doc: 'Stack arrays along NEW axis.' },
            vstack:     { sig: 'vstack(tup)',                          doc: 'Vertical stack (row-wise).' },
            hstack:     { sig: 'hstack(tup)',                          doc: 'Horizontal stack (column-wise).' },
            split:      { sig: 'split(ary, indices_or_sections, axis=0)', doc: 'Split an array into multiple sub-arrays.' },
            repeat:     { sig: 'repeat(a, repeats, axis=None)',        doc: 'Repeat elements.' },
            tile:       { sig: 'tile(A, reps)',                        doc: 'Tile array.' },
            // Math
            sum:        { sig: 'sum(a, axis=None, dtype=None, keepdims=False)', doc: 'Sum along an axis.' },
            mean:       { sig: 'mean(a, axis=None)',                   doc: 'Arithmetic mean.' },
            median:     { sig: 'median(a, axis=None)',                 doc: 'Median value.' },
            std:        { sig: 'std(a, axis=None, ddof=0)',            doc: 'Standard deviation.' },
            var:        { sig: 'var(a, axis=None, ddof=0)',            doc: 'Variance.' },
            min:        { sig: 'min(a, axis=None)',                    doc: 'Minimum value.' },
            max:        { sig: 'max(a, axis=None)',                    doc: 'Maximum value.' },
            argmin:     { sig: 'argmin(a, axis=None)',                 doc: 'Index of minimum.' },
            argmax:     { sig: 'argmax(a, axis=None)',                 doc: 'Index of maximum.' },
            sort:       { sig: 'sort(a, axis=-1, kind=None)',          doc: 'Return sorted copy.' },
            argsort:    { sig: 'argsort(a, axis=-1)',                  doc: 'Indices that would sort the array.' },
            unique:     { sig: 'unique(ar, return_index=False, return_counts=False)', doc: 'Unique elements.' },
            where:      { sig: 'where(condition[, x, y])',             doc: 'Return x where True else y; with one arg, returns indices.' },
            // Linear algebra
            dot:        { sig: 'dot(a, b)',                            doc: 'Dot product.' },
            matmul:     { sig: 'matmul(a, b)',                         doc: 'Matrix product (same as `@`).' },
            cross:      { sig: 'cross(a, b)',                          doc: 'Cross product.' },
            linalg:     { sig: 'linalg', kind: 'mod',                  doc: 'Linear algebra: `inv`, `det`, `eig`, `svd`, `solve`, `norm`.' },
            inner:      { sig: 'inner(a, b)',                          doc: 'Inner product.' },
            outer:      { sig: 'outer(a, b)',                          doc: 'Outer product.' },
            // Trig / math
            sin:        { sig: 'sin(x)',                               doc: 'Sine (radians).' },
            cos:        { sig: 'cos(x)',                               doc: 'Cosine (radians).' },
            tan:        { sig: 'tan(x)',                               doc: 'Tangent (radians).' },
            arcsin:     { sig: 'arcsin(x)',                            doc: 'Arc sine.' },
            arccos:     { sig: 'arccos(x)',                            doc: 'Arc cosine.' },
            arctan:     { sig: 'arctan(x)',                            doc: 'Arc tangent.' },
            arctan2:    { sig: 'arctan2(y, x)',                        doc: 'Arc tangent of y/x, with quadrant awareness.' },
            sinh:       { sig: 'sinh(x)',                              doc: 'Hyperbolic sine.' },
            cosh:       { sig: 'cosh(x)',                              doc: 'Hyperbolic cosine.' },
            exp:        { sig: 'exp(x)',                               doc: 'Elementwise exponential e^x.' },
            log:        { sig: 'log(x)',                               doc: 'Natural log.' },
            log2:       { sig: 'log2(x)',                              doc: 'Base-2 log.' },
            log10:      { sig: 'log10(x)',                             doc: 'Base-10 log.' },
            sqrt:       { sig: 'sqrt(x)',                              doc: 'Square root.' },
            abs:        { sig: 'abs(x)',                               doc: 'Elementwise absolute value.' },
            floor:      { sig: 'floor(x)',                             doc: 'Floor.' },
            ceil:       { sig: 'ceil(x)',                              doc: 'Ceiling.' },
            clip:       { sig: 'clip(a, a_min, a_max)',                doc: 'Clip values to range.' },
            // Constants
            pi:         { sig: 'pi ≈ 3.14159',                         doc: 'π', kind: 'const' },
            e:          { sig: 'e ≈ 2.71828',                          doc: 'Euler\'s number.', kind: 'const' },
            inf:        { sig: 'inf',                                  doc: 'Floating-point positive infinity.', kind: 'const' },
            nan:        { sig: 'nan',                                  doc: 'Floating-point NaN.', kind: 'const' },
            ndarray:    { sig: 'ndarray',                              doc: 'N-dimensional array class.', kind: 'class' },
            dtype:      { sig: 'dtype(obj)',                           doc: 'Data type object.', kind: 'class' },
        },

        // ── matplotlib.pyplot (plt.*) ───────────────────────────────────────
        'matplotlib.pyplot': {
            plot:       { sig: 'plot(*args, scalex=True, scaley=True, data=None, **kwargs)', doc: 'Plot y vs x.\n```python\nplt.plot(x, y, "r--", label="sin")\nplt.legend()\nplt.show()\n```' },
            scatter:    { sig: 'scatter(x, y, s=None, c=None, marker=None)', doc: 'Scatter plot.' },
            bar:        { sig: 'bar(x, height, width=0.8, bottom=None, align="center")', doc: 'Vertical bar chart.' },
            barh:       { sig: 'barh(y, width, height=0.8)',           doc: 'Horizontal bar chart.' },
            hist:       { sig: 'hist(x, bins=None, range=None, density=False)', doc: 'Histogram.' },
            pie:        { sig: 'pie(x, labels=None, colors=None, autopct=None)', doc: 'Pie chart.' },
            imshow:     { sig: 'imshow(X, cmap=None, aspect=None, interpolation=None)', doc: 'Display 2-D array as image.' },
            contour:    { sig: 'contour(X, Y, Z, levels=None)',        doc: 'Contour plot.' },
            contourf:   { sig: 'contourf(X, Y, Z, levels=None)',       doc: 'Filled contour plot.' },
            quiver:     { sig: 'quiver(X, Y, U, V, C=None)',           doc: 'Vector field.' },
            figure:     { sig: 'figure(num=None, figsize=None, dpi=None)', doc: 'Create new figure.' },
            subplots:   { sig: 'subplots(nrows=1, ncols=1, figsize=None, sharex=False, sharey=False)', doc: 'Create figure and axes.\n```python\nfig, ax = plt.subplots(2, 2, figsize=(10, 8))\n```' },
            subplot:    { sig: 'subplot(nrows, ncols, index)',         doc: 'Add a subplot.' },
            show:       { sig: 'show(block=None)',                     doc: 'Display all figures.' },
            savefig:    { sig: 'savefig(fname, dpi="figure", format=None, bbox_inches=None)', doc: 'Save figure to file.' },
            close:      { sig: 'close(fig=None)',                      doc: 'Close figure(s).' },
            clf:        { sig: 'clf()',                                doc: 'Clear current figure.' },
            cla:        { sig: 'cla()',                                doc: 'Clear current axes.' },
            title:      { sig: 'title(label, fontdict=None, loc="center")', doc: 'Set axes title.' },
            suptitle:   { sig: 'suptitle(t, fontsize="large")',        doc: 'Figure-level title.' },
            xlabel:     { sig: 'xlabel(xlabel, fontdict=None)',        doc: 'Set x-axis label.' },
            ylabel:     { sig: 'ylabel(ylabel, fontdict=None)',        doc: 'Set y-axis label.' },
            xlim:       { sig: 'xlim(left=None, right=None)',          doc: 'Get/set x-axis limits.' },
            ylim:       { sig: 'ylim(bottom=None, top=None)',          doc: 'Get/set y-axis limits.' },
            xticks:     { sig: 'xticks(ticks=None, labels=None)',      doc: 'Get/set x-axis ticks.' },
            yticks:     { sig: 'yticks(ticks=None, labels=None)',      doc: 'Get/set y-axis ticks.' },
            legend:     { sig: 'legend(*args, **kwargs)',              doc: 'Place a legend.' },
            grid:       { sig: 'grid(visible=None, which="major", axis="both")', doc: 'Toggle gridlines.' },
            axis:       { sig: 'axis(*args, **kwargs)',                doc: 'Get/set axis properties.' },
            text:       { sig: 'text(x, y, s, fontdict=None)',         doc: 'Add text at (x, y).' },
            annotate:   { sig: 'annotate(text, xy, xytext=None, arrowprops=None)', doc: 'Annotate with optional arrow.' },
            axhline:    { sig: 'axhline(y=0, xmin=0, xmax=1)',         doc: 'Horizontal line.' },
            axvline:    { sig: 'axvline(x=0, ymin=0, ymax=1)',         doc: 'Vertical line.' },
            fill_between: { sig: 'fill_between(x, y1, y2=0, where=None, alpha=None)', doc: 'Fill area between curves.' },
            colorbar:   { sig: 'colorbar(mappable=None, ax=None)',     doc: 'Add colorbar.' },
            tight_layout:{ sig: 'tight_layout(pad=1.08)',              doc: 'Auto-adjust subplots.' },
            style:      { sig: 'style.use(name)',                      doc: 'Apply a matplotlib stylesheet.', kind: 'mod' },
        },

        // ── math ────────────────────────────────────────────────────────────
        math: {
            pi:         { sig: 'pi ≈ 3.14159', doc: 'π', kind: 'const' },
            e:          { sig: 'e ≈ 2.71828', doc: 'Euler\'s number.', kind: 'const' },
            tau:        { sig: 'tau = 2π ≈ 6.28318', doc: '2π', kind: 'const' },
            inf:        { sig: 'inf',  doc: 'Positive infinity.', kind: 'const' },
            nan:        { sig: 'nan',  doc: 'NaN.', kind: 'const' },
            sqrt:       { sig: 'sqrt(x)',                   doc: 'Square root of x.' },
            pow:        { sig: 'pow(x, y)',                 doc: 'x ** y.' },
            exp:        { sig: 'exp(x)',                    doc: 'e ** x.' },
            log:        { sig: 'log(x, base=math.e)',       doc: 'Logarithm.' },
            log2:       { sig: 'log2(x)',                   doc: 'Base-2 log.' },
            log10:      { sig: 'log10(x)',                  doc: 'Base-10 log.' },
            sin:        { sig: 'sin(x)',                    doc: 'Sine.' },
            cos:        { sig: 'cos(x)',                    doc: 'Cosine.' },
            tan:        { sig: 'tan(x)',                    doc: 'Tangent.' },
            asin:       { sig: 'asin(x)',                   doc: 'Arc sine.' },
            acos:       { sig: 'acos(x)',                   doc: 'Arc cosine.' },
            atan:       { sig: 'atan(x)',                   doc: 'Arc tangent.' },
            atan2:      { sig: 'atan2(y, x)',               doc: 'atan(y/x) with quadrant.' },
            sinh:       { sig: 'sinh(x)',                   doc: 'Hyperbolic sine.' },
            cosh:       { sig: 'cosh(x)',                   doc: 'Hyperbolic cosine.' },
            tanh:       { sig: 'tanh(x)',                   doc: 'Hyperbolic tangent.' },
            floor:      { sig: 'floor(x)',                  doc: 'Largest integer ≤ x.' },
            ceil:       { sig: 'ceil(x)',                   doc: 'Smallest integer ≥ x.' },
            trunc:      { sig: 'trunc(x)',                  doc: 'Truncate toward zero.' },
            fabs:       { sig: 'fabs(x)',                   doc: 'Float absolute value.' },
            factorial:  { sig: 'factorial(x)',              doc: 'x!.' },
            gcd:        { sig: 'gcd(*integers)',            doc: 'Greatest common divisor.' },
            lcm:        { sig: 'lcm(*integers)',            doc: 'Least common multiple.' },
            isclose:    { sig: 'isclose(a, b, rel_tol=1e-09, abs_tol=0.0)', doc: 'Near-equality comparison.' },
            isnan:      { sig: 'isnan(x)',                  doc: 'Is x NaN?' },
            isinf:      { sig: 'isinf(x)',                  doc: 'Is x infinite?' },
            degrees:    { sig: 'degrees(x)',                doc: 'Radians → degrees.' },
            radians:    { sig: 'radians(x)',                doc: 'Degrees → radians.' },
            hypot:      { sig: 'hypot(*coords)',            doc: 'Euclidean norm.' },
            comb:       { sig: 'comb(n, k)',                doc: 'Binomial coefficient.' },
            perm:       { sig: 'perm(n, k=None)',           doc: 'Permutations.' },
        },

        // ── random ──────────────────────────────────────────────────────────
        random: {
            random:     { sig: 'random()',                  doc: 'Float in [0.0, 1.0).' },
            seed:       { sig: 'seed(a=None)',              doc: 'Seed the generator.' },
            randint:    { sig: 'randint(a, b)',             doc: 'Integer N where a <= N <= b (inclusive).' },
            randrange:  { sig: 'randrange(start, stop=None, step=1)', doc: 'Random from range.' },
            choice:     { sig: 'choice(seq)',               doc: 'Random element.' },
            choices:    { sig: 'choices(population, weights=None, k=1)', doc: 'k elements with replacement.' },
            sample:     { sig: 'sample(population, k)',     doc: 'k unique elements.' },
            shuffle:    { sig: 'shuffle(x)',                doc: 'Shuffle list in-place.' },
            uniform:    { sig: 'uniform(a, b)',             doc: 'Float in [a, b].' },
            gauss:      { sig: 'gauss(mu, sigma)',          doc: 'Gaussian distribution.' },
            normalvariate:{ sig: 'normalvariate(mu, sigma)',doc: 'Normal distribution.' },
            expovariate:{ sig: 'expovariate(lambd)',        doc: 'Exponential distribution.' },
            triangular: { sig: 'triangular(low=0.0, high=1.0, mode=None)', doc: 'Triangular distribution.' },
        },

        // ── os ──────────────────────────────────────────────────────────────
        os: {
            getcwd:     { sig: 'getcwd()',                  doc: 'Current working directory.' },
            chdir:      { sig: 'chdir(path)',               doc: 'Change cwd.' },
            listdir:    { sig: 'listdir(path=".")',         doc: 'List entries in directory.' },
            mkdir:      { sig: 'mkdir(path, mode=0o777)',   doc: 'Create directory.' },
            makedirs:   { sig: 'makedirs(name, exist_ok=False)', doc: 'Create directory (with parents).' },
            rmdir:      { sig: 'rmdir(path)',               doc: 'Remove directory.' },
            remove:     { sig: 'remove(path)',              doc: 'Delete file.' },
            unlink:     { sig: 'unlink(path)',              doc: 'Alias for remove().' },
            rename:     { sig: 'rename(src, dst)',          doc: 'Rename file.' },
            path:       { sig: 'path', kind: 'mod',         doc: 'os.path: join, exists, isfile, isdir, dirname, basename, ...' },
            environ:    { sig: 'environ',                   doc: 'Environment variables dict.', kind: 'const' },
            getenv:     { sig: 'getenv(key, default=None)', doc: 'Get environment variable.' },
            putenv:     { sig: 'putenv(key, value)',        doc: 'Set environment variable.' },
            walk:       { sig: 'walk(top, topdown=True)',   doc: 'Recursive directory walk. Yields (root, dirs, files).' },
            sep:        { sig: 'sep',                       doc: 'Path separator ("/" on Unix).', kind: 'const' },
            linesep:    { sig: 'linesep',                   doc: 'Platform line ending.', kind: 'const' },
            name:       { sig: 'name',                      doc: 'OS name: "posix" / "nt".', kind: 'const' },
        },

        // ── sys ─────────────────────────────────────────────────────────────
        sys: {
            argv:       { sig: 'argv',                      doc: 'Command-line arguments list.', kind: 'const' },
            path:       { sig: 'path',                      doc: 'Module search paths list.', kind: 'const' },
            platform:   { sig: 'platform',                  doc: 'Platform identifier.', kind: 'const' },
            version:    { sig: 'version',                   doc: 'Python version string.', kind: 'const' },
            version_info:{ sig: 'version_info',             doc: 'Tuple version: (major, minor, micro, ...)', kind: 'const' },
            stdout:     { sig: 'stdout',                    doc: 'Standard output.', kind: 'const' },
            stderr:     { sig: 'stderr',                    doc: 'Standard error.', kind: 'const' },
            stdin:      { sig: 'stdin',                     doc: 'Standard input.', kind: 'const' },
            exit:       { sig: 'exit(status=0)',            doc: 'Exit interpreter.' },
            modules:    { sig: 'modules',                   doc: 'Dict of loaded modules.', kind: 'const' },
            maxsize:    { sig: 'maxsize',                   doc: 'Largest Py_ssize_t.', kind: 'const' },
        },

        // ── re ──────────────────────────────────────────────────────────────
        re: {
            match:      { sig: 'match(pattern, string, flags=0)',      doc: 'Match at START of string.' },
            search:     { sig: 'search(pattern, string, flags=0)',     doc: 'Search for first match.' },
            findall:    { sig: 'findall(pattern, string, flags=0)',    doc: 'Return all non-overlapping matches.' },
            finditer:   { sig: 'finditer(pattern, string, flags=0)',   doc: 'Iterator of Match objects.' },
            sub:        { sig: 'sub(pattern, repl, string, count=0, flags=0)', doc: 'Replace matches.' },
            split:      { sig: 'split(pattern, string, maxsplit=0, flags=0)', doc: 'Split by pattern.' },
            compile:    { sig: 'compile(pattern, flags=0)',            doc: 'Compile into a Pattern object.' },
            escape:     { sig: 'escape(string)',                       doc: 'Escape regex metacharacters.' },
            fullmatch:  { sig: 'fullmatch(pattern, string, flags=0)',  doc: 'Match the ENTIRE string.' },
            IGNORECASE: { sig: 'IGNORECASE', kind: 'const',            doc: 'Case-insensitive flag.' },
            MULTILINE:  { sig: 'MULTILINE',  kind: 'const',            doc: 'Multiline mode.' },
            DOTALL:     { sig: 'DOTALL',     kind: 'const',            doc: 'Dot matches newline.' },
            VERBOSE:    { sig: 'VERBOSE',    kind: 'const',            doc: 'Verbose regex mode.' },
        },

        // ── json ────────────────────────────────────────────────────────────
        json: {
            loads:      { sig: 'loads(s, **kwargs)',                   doc: 'Parse JSON string → object.' },
            dumps:      { sig: 'dumps(obj, indent=None, ensure_ascii=True)', doc: 'Serialize object → JSON string.' },
            load:       { sig: 'load(fp, **kwargs)',                   doc: 'Parse JSON from file-like.' },
            dump:       { sig: 'dump(obj, fp, indent=None)',           doc: 'Write JSON to file-like.' },
            JSONDecoder:{ sig: 'JSONDecoder',                          doc: 'Decoder class.', kind: 'class' },
            JSONEncoder:{ sig: 'JSONEncoder',                          doc: 'Encoder class.', kind: 'class' },
        },

        // ── datetime ────────────────────────────────────────────────────────
        datetime: {
            datetime:   { sig: 'datetime(year, month, day, hour=0, minute=0, second=0, microsecond=0, tzinfo=None)', doc: 'Combined date and time.', kind: 'class' },
            date:       { sig: 'date(year, month, day)',               doc: 'Date object.', kind: 'class' },
            time:       { sig: 'time(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)', doc: 'Time object.', kind: 'class' },
            timedelta:  { sig: 'timedelta(days=0, seconds=0, microseconds=0, milliseconds=0, minutes=0, hours=0, weeks=0)', doc: 'Duration.', kind: 'class' },
            timezone:   { sig: 'timezone(offset, name=None)',          doc: 'Fixed UTC offset.', kind: 'class' },
            now:        { sig: 'datetime.now(tz=None)',                doc: 'Current local datetime.' },
            utcnow:     { sig: 'datetime.utcnow()',                    doc: 'Current UTC datetime.' },
            today:      { sig: 'datetime.today()',                     doc: 'Current local datetime.' },
            fromtimestamp:{ sig: 'datetime.fromtimestamp(ts, tz=None)',doc: 'From Unix timestamp.' },
            strptime:   { sig: 'datetime.strptime(date_string, format)', doc: 'Parse string with format.' },
        },

        // ── collections ─────────────────────────────────────────────────────
        collections: {
            defaultdict:{ sig: 'defaultdict(default_factory=None)',    doc: 'Dict with default factory.\n```python\nd = defaultdict(list)\nd["x"].append(1)\n```', kind: 'class' },
            Counter:    { sig: 'Counter(iterable=None)',               doc: 'Dict subclass for counting hashables.\n```python\nCounter("abracadabra").most_common(3)\n```', kind: 'class' },
            OrderedDict:{ sig: 'OrderedDict(items=None)',              doc: 'Dict that remembers insertion order (all Python 3 dicts do now).', kind: 'class' },
            deque:      { sig: 'deque(iterable=(), maxlen=None)',      doc: 'Double-ended queue.', kind: 'class' },
            namedtuple: { sig: 'namedtuple(typename, field_names)',    doc: 'Factory for tuple subclasses with named fields.\n```python\nPoint = namedtuple("Point", ["x", "y"])\n```' },
            ChainMap:   { sig: 'ChainMap(*maps)',                      doc: 'Link multiple dicts into a single view.', kind: 'class' },
        },

        // ── itertools ───────────────────────────────────────────────────────
        itertools: {
            count:      { sig: 'count(start=0, step=1)',               doc: 'Infinite arithmetic progression.' },
            cycle:      { sig: 'cycle(iterable)',                      doc: 'Repeat iterable forever.' },
            repeat:     { sig: 'repeat(object, times=None)',           doc: 'Repeat an object.' },
            chain:      { sig: 'chain(*iterables)',                    doc: 'Chain iterables end-to-end.' },
            combinations:{ sig: 'combinations(iterable, r)',           doc: 'All r-length combinations.' },
            combinations_with_replacement: { sig: 'combinations_with_replacement(iterable, r)', doc: 'Combinations allowing repeats.' },
            permutations:{ sig: 'permutations(iterable, r=None)',      doc: 'All r-length permutations.' },
            product:    { sig: 'product(*iterables, repeat=1)',        doc: 'Cartesian product.' },
            groupby:    { sig: 'groupby(iterable, key=None)',          doc: 'Group consecutive elements.' },
            islice:     { sig: 'islice(iterable, stop)',               doc: 'Slice an iterator.' },
            accumulate: { sig: 'accumulate(iterable, func=operator.add, *, initial=None)', doc: 'Running totals.' },
            takewhile:  { sig: 'takewhile(predicate, iterable)',       doc: 'Take while predicate is true.' },
            dropwhile:  { sig: 'dropwhile(predicate, iterable)',       doc: 'Drop while predicate is true.' },
            starmap:    { sig: 'starmap(function, iterable)',          doc: 'Like map(), but args are tuples unpacked with *.' },
            zip_longest:{ sig: 'zip_longest(*iterables, fillvalue=None)', doc: 'Zip to longest iterable.' },
        },

        // ── functools ───────────────────────────────────────────────────────
        functools: {
            reduce:     { sig: 'reduce(function, iterable[, initializer])', doc: 'Apply function cumulatively.\n```python\nreduce(lambda a,b: a+b, [1,2,3,4])  # 10\n```' },
            partial:    { sig: 'partial(func, *args, **keywords)',     doc: 'Partial function application.' },
            lru_cache:  { sig: 'lru_cache(maxsize=128, typed=False)',  doc: 'Decorator: memoize results with LRU eviction.' },
            cache:      { sig: 'cache(user_function)',                 doc: 'Unlimited memoization decorator.' },
            wraps:      { sig: 'wraps(wrapped)',                       doc: 'Decorator factory — preserves metadata when wrapping.' },
            cmp_to_key: { sig: 'cmp_to_key(func)',                     doc: 'Convert cmp function to key function.' },
            singledispatch: { sig: 'singledispatch(func)',             doc: 'Single-dispatch generic function decorator.' },
        },

        // ── requests ────────────────────────────────────────────────────────
        requests: {
            get:        { sig: 'get(url, params=None, **kwargs)',      doc: 'GET request.\n```python\nr = requests.get(url, params={"q": "ai"})\nr.json()\n```' },
            post:       { sig: 'post(url, data=None, json=None, **kwargs)', doc: 'POST request.' },
            put:        { sig: 'put(url, data=None, **kwargs)',        doc: 'PUT request.' },
            delete:     { sig: 'delete(url, **kwargs)',                doc: 'DELETE request.' },
            head:       { sig: 'head(url, **kwargs)',                  doc: 'HEAD request.' },
            patch:      { sig: 'patch(url, data=None, **kwargs)',      doc: 'PATCH request.' },
            request:    { sig: 'request(method, url, **kwargs)',       doc: 'Generic HTTP request.' },
            Session:    { sig: 'Session()',                            doc: 'Persistent session with cookie jar.', kind: 'class' },
        },

        // ── scipy (top-level sp.*) ──────────────────────────────────────────
        scipy: {
            optimize:   { sig: 'optimize', kind: 'mod',                doc: 'Optimization: minimize, curve_fit, least_squares, ...' },
            integrate:  { sig: 'integrate', kind: 'mod',               doc: 'Integration: quad, dblquad, odeint, solve_ivp.' },
            stats:      { sig: 'stats', kind: 'mod',                   doc: 'Statistics: distributions, t-test, chi2, linregress.' },
            signal:     { sig: 'signal', kind: 'mod',                  doc: 'Signal processing: fft, convolve, filter design.' },
            linalg:     { sig: 'linalg', kind: 'mod',                  doc: 'Linear algebra: inv, svd, eig, solve.' },
            sparse:     { sig: 'sparse', kind: 'mod',                  doc: 'Sparse matrices.' },
            interpolate:{ sig: 'interpolate', kind: 'mod',             doc: 'Interpolation: interp1d, interp2d, splrep.' },
            spatial:    { sig: 'spatial', kind: 'mod',                 doc: 'Spatial algorithms: KDTree, distance, Delaunay.' },
            fft:        { sig: 'fft', kind: 'mod',                     doc: 'Fast Fourier Transform.' },
        },

        // ── sympy (sym.*) ───────────────────────────────────────────────────
        sympy: {
            symbols:    { sig: 'symbols(names, **kwargs)',             doc: 'Create symbolic variables.\n```python\nx, y = symbols("x y")\n```' },
            Symbol:     { sig: 'Symbol(name, **kwargs)',               doc: 'Single symbolic variable.', kind: 'class' },
            simplify:   { sig: 'simplify(expr)',                       doc: 'Simplify expression.' },
            expand:     { sig: 'expand(expr)',                         doc: 'Expand expression.' },
            factor:     { sig: 'factor(expr)',                         doc: 'Factor expression.' },
            solve:      { sig: 'solve(expr, *symbols)',                doc: 'Solve equation(s).\n```python\nsolve(x**2 - 4, x)  # [-2, 2]\n```' },
            diff:       { sig: 'diff(expr, *symbols)',                 doc: 'Differentiate.' },
            integrate:  { sig: 'integrate(expr, *symbols)',            doc: 'Integrate (symbolic).' },
            limit:      { sig: 'limit(expr, z, z0, dir="+")',          doc: 'Compute a limit.' },
            series:     { sig: 'series(expr, x=None, x0=0, n=6)',      doc: 'Taylor series expansion.' },
            Matrix:     { sig: 'Matrix(data)',                         doc: 'Symbolic matrix.', kind: 'class' },
            sin:        { sig: 'sin(x)',                               doc: 'Symbolic sine.' },
            cos:        { sig: 'cos(x)',                               doc: 'Symbolic cosine.' },
            exp:        { sig: 'exp(x)',                               doc: 'Symbolic exp.' },
            log:        { sig: 'log(x, base=E)',                       doc: 'Symbolic log.' },
            sqrt:       { sig: 'sqrt(x)',                              doc: 'Symbolic sqrt.' },
            pi:         { sig: 'pi',                                   doc: 'Symbolic π.', kind: 'const' },
            E:          { sig: 'E',                                    doc: 'Symbolic Euler\'s number.', kind: 'const' },
            I:          { sig: 'I',                                    doc: 'Imaginary unit.', kind: 'const' },
            oo:         { sig: 'oo',                                   doc: 'Infinity.', kind: 'const' },
            Rational:   { sig: 'Rational(p, q=1)',                     doc: 'Exact rational number.', kind: 'class' },
            Eq:         { sig: 'Eq(lhs, rhs)',                         doc: 'Equality expression.', kind: 'class' },
            latex:      { sig: 'latex(expr)',                          doc: 'Convert to LaTeX string.' },
        },

        // ── tqdm ────────────────────────────────────────────────────────────
        tqdm: {
            tqdm:       { sig: 'tqdm(iterable=None, desc=None, total=None, leave=True, ncols=None)', doc: 'Progress bar wrapper.\n```python\nfor x in tqdm(range(1000)):\n    do_work(x)\n```', kind: 'class' },
            trange:     { sig: 'trange(*args, **kwargs)',              doc: 'Shortcut for tqdm(range(*args)).' },
        },

        // ── torch ───────────────────────────────────────────────────────────
        torch: {
            tensor:     { sig: 'tensor(data, dtype=None, device=None, requires_grad=False)', doc: 'Construct a tensor from data.\n```python\nx = torch.tensor([[1, 2], [3, 4]], dtype=torch.float32)\n```' },
            zeros:      { sig: 'zeros(*size, dtype=None, device=None)', doc: 'Tensor filled with 0.' },
            ones:       { sig: 'ones(*size, dtype=None, device=None)',  doc: 'Tensor filled with 1.' },
            empty:      { sig: 'empty(*size, dtype=None)',              doc: 'Uninitialized tensor.' },
            arange:     { sig: 'arange(start, end=None, step=1)',       doc: 'Like Python range, returns 1-D tensor.' },
            linspace:   { sig: 'linspace(start, end, steps)',           doc: 'Linearly spaced tensor.' },
            randn:      { sig: 'randn(*size)',                          doc: 'Normal(0,1) random tensor.' },
            rand:       { sig: 'rand(*size)',                           doc: 'Uniform[0,1) random tensor.' },
            randint:    { sig: 'randint(low, high, size)',              doc: 'Uniform integers tensor.' },
            from_numpy: { sig: 'from_numpy(ndarray)',                   doc: 'Zero-copy bridge from NumPy array.' },
            cat:        { sig: 'cat(tensors, dim=0)',                   doc: 'Concatenate tensors along dim.' },
            stack:      { sig: 'stack(tensors, dim=0)',                 doc: 'Stack tensors along a new dim.' },
            matmul:     { sig: 'matmul(a, b)',                          doc: 'Matrix product (`a @ b`).' },
            no_grad:    { sig: 'no_grad()',                             doc: 'Context manager: disable autograd.\n```python\nwith torch.no_grad():\n    out = model(x)\n```' },
            inference_mode: { sig: 'inference_mode()',                  doc: 'Faster than no_grad for inference.' },
            save:       { sig: 'save(obj, f)',                          doc: 'Serialize tensor / state_dict to disk.' },
            load:       { sig: 'load(f, map_location=None, weights_only=False)', doc: 'Load serialized object.' },
            nn:         { sig: 'nn',                                    doc: 'Neural network building blocks.', kind: 'mod' },
            optim:      { sig: 'optim',                                 doc: 'Optimizers (SGD, Adam, …).', kind: 'mod' },
            device:     { sig: 'device(name)',                          doc: '`torch.device("cpu")` etc. (no CUDA on iOS).', kind: 'class' },
            float32:    { sig: 'float32',                               doc: '32-bit float dtype.', kind: 'const' },
            float16:    { sig: 'float16',                               doc: '16-bit float dtype.', kind: 'const' },
            int64:      { sig: 'int64',                                 doc: '64-bit int dtype.', kind: 'const' },
            bool:       { sig: 'bool',                                  doc: 'Boolean dtype.', kind: 'const' },
        },

        // ── transformers ────────────────────────────────────────────────────
        transformers: {
            AutoModel:           { sig: 'AutoModel.from_pretrained(name_or_path, **kw)', doc: 'Load any model architecture by name.', kind: 'class' },
            AutoModelForCausalLM:{ sig: 'AutoModelForCausalLM.from_pretrained(name_or_path)', doc: 'Causal LM (GPT-style).', kind: 'class' },
            AutoModelForSequenceClassification: { sig: 'AutoModelForSequenceClassification.from_pretrained(name)', doc: 'Sequence classifier.', kind: 'class' },
            AutoTokenizer:       { sig: 'AutoTokenizer.from_pretrained(name_or_path)', doc: 'Auto-detect & load the right tokenizer.', kind: 'class' },
            AutoConfig:          { sig: 'AutoConfig.from_pretrained(name_or_path)', doc: 'Load a model config.', kind: 'class' },
            pipeline:            { sig: 'pipeline(task, model=None, **kw)', doc: 'High-level inference pipeline.\n```python\np = pipeline("text-generation", model="gpt2")\n```' },
            GenerationConfig:    { sig: 'GenerationConfig(**kw)',         doc: 'Generation params (temperature, top_p, …).', kind: 'class' },
            TextStreamer:        { sig: 'TextStreamer(tokenizer)',        doc: 'Print generated tokens as they stream.', kind: 'class' },
        },

        // ── huggingface_hub ─────────────────────────────────────────────────
        huggingface_hub: {
            snapshot_download:   { sig: 'snapshot_download(repo_id, cache_dir=None, local_dir=None, allow_patterns=None)', doc: 'Download an entire HF repo to disk.' },
            hf_hub_download:     { sig: 'hf_hub_download(repo_id, filename, cache_dir=None)', doc: 'Download a single file from a repo.' },
            login:               { sig: 'login(token=None)',              doc: 'Authenticate with the HF Hub.' },
            HfApi:               { sig: 'HfApi(endpoint=None, token=None)', doc: 'Low-level Hub HTTP client.', kind: 'class' },
            list_models:         { sig: 'list_models(filter=None, search=None, limit=None)', doc: 'Search models on the Hub.' },
            model_info:          { sig: 'model_info(repo_id, revision=None)', doc: 'Metadata for a single repo.' },
        },

        // ── manim ───────────────────────────────────────────────────────────
        manim: {
            Scene:      { sig: 'Scene()',                              doc: 'Base class for all manim scenes.\n```python\nclass MyScene(Scene):\n    def construct(self):\n        self.play(Create(Circle()))\n```', kind: 'class' },
            Mobject:    { sig: 'Mobject()',                            doc: 'Base mathematical object.', kind: 'class' },
            VMobject:   { sig: 'VMobject()',                           doc: 'Vectorized mobject.', kind: 'class' },
            Circle:     { sig: 'Circle(radius=1.0, color=WHITE)',      doc: 'A circle.', kind: 'class' },
            Square:     { sig: 'Square(side_length=2.0, color=WHITE)', doc: 'A square.', kind: 'class' },
            Rectangle:  { sig: 'Rectangle(width=4, height=2)',         doc: 'A rectangle.', kind: 'class' },
            Triangle:   { sig: 'Triangle()',                           doc: 'Equilateral triangle.', kind: 'class' },
            Line:       { sig: 'Line(start, end, color=WHITE)',        doc: 'A line segment.', kind: 'class' },
            Arrow:      { sig: 'Arrow(start, end, buff=0.25)',         doc: 'An arrow.', kind: 'class' },
            Dot:        { sig: 'Dot(point=ORIGIN, radius=0.08)',       doc: 'A small dot.', kind: 'class' },
            Text:       { sig: 'Text(text, font="", font_size=48)',    doc: 'Pango-rendered text (multi-script).', kind: 'class' },
            MathTex:    { sig: 'MathTex(*tex_strings)',                doc: 'LaTeX math via offlinai_latex.', kind: 'class' },
            Tex:        { sig: 'Tex(*tex_strings)',                    doc: 'LaTeX text mode.', kind: 'class' },
            VGroup:     { sig: 'VGroup(*mobjects)',                    doc: 'Group of vectorized mobjects.', kind: 'class' },
            Create:     { sig: 'Create(mobject, **kwargs)',            doc: 'Animate creation of mobject.', kind: 'class' },
            Write:      { sig: 'Write(mobject)',                       doc: 'Animate writing of text/math.', kind: 'class' },
            FadeIn:     { sig: 'FadeIn(mobject)',                      doc: 'Fade in animation.', kind: 'class' },
            FadeOut:    { sig: 'FadeOut(mobject)',                     doc: 'Fade out animation.', kind: 'class' },
            Transform:  { sig: 'Transform(mobject, target_mobject)',   doc: 'Morph one mobject into another.', kind: 'class' },
            ReplacementTransform: { sig: 'ReplacementTransform(m1, m2)', doc: 'Transform that replaces source.', kind: 'class' },
            UP:         { sig: 'UP',                                   doc: 'Unit vector [0, 1, 0].',  kind: 'const' },
            DOWN:       { sig: 'DOWN',                                 doc: 'Unit vector [0, -1, 0].', kind: 'const' },
            LEFT:       { sig: 'LEFT',                                 doc: 'Unit vector [-1, 0, 0].', kind: 'const' },
            RIGHT:      { sig: 'RIGHT',                                doc: 'Unit vector [1, 0, 0].',  kind: 'const' },
            ORIGIN:     { sig: 'ORIGIN',                               doc: '[0, 0, 0].',              kind: 'const' },
            WHITE:      { sig: 'WHITE',                                doc: 'Color WHITE.',            kind: 'const' },
            BLACK:      { sig: 'BLACK',                                doc: 'Color BLACK.',            kind: 'const' },
            RED:        { sig: 'RED',                                  doc: 'Color RED.',              kind: 'const' },
            GREEN:      { sig: 'GREEN',                                doc: 'Color GREEN.',            kind: 'const' },
            BLUE:       { sig: 'BLUE',                                 doc: 'Color BLUE.',             kind: 'const' },
            YELLOW:     { sig: 'YELLOW',                               doc: 'Color YELLOW.',           kind: 'const' },
        },

        // ── rich ────────────────────────────────────────────────────────────
        rich: {
            print:      { sig: 'print(*objects, **kwargs)',            doc: 'Pretty-printer with markup, colors.\n```python\nrich.print("[bold red]hi[/]")\n```' },
            inspect:    { sig: 'inspect(obj, methods=False, help=False)', doc: 'Pretty-print an object\'s attributes.' },
            Console:    { sig: 'Console(**kwargs)',                    doc: 'Main entry-point for rich rendering.', kind: 'class' },
            Markdown:   { sig: 'Markdown(markup)',                     doc: 'Render a Markdown string.', kind: 'class' },
            Table:      { sig: 'Table(title=None, **kwargs)',          doc: 'Pretty tables.', kind: 'class' },
            Panel:      { sig: 'Panel(renderable, title=None)',        doc: 'Rectangular panel.', kind: 'class' },
            Progress:   { sig: 'Progress(*columns)',                   doc: 'Progress bar context manager.', kind: 'class' },
            Live:       { sig: 'Live(renderable, refresh_per_second=4)', doc: 'Live-updating renderable.', kind: 'class' },
            Syntax:     { sig: 'Syntax(code, lexer, theme="monokai")', doc: 'Syntax-highlighted code block.', kind: 'class' },
            Tree:       { sig: 'Tree(label, **kwargs)',                doc: 'Hierarchical tree display.', kind: 'class' },
        },

        // ── bs4 (BeautifulSoup) ─────────────────────────────────────────────
        bs4: {
            BeautifulSoup: { sig: 'BeautifulSoup(markup, features="html.parser")', doc: 'Parse HTML/XML.\n```python\nsoup = BeautifulSoup(html, "html.parser")\nlinks = soup.select("a[href]")\n```', kind: 'class' },
            SoupStrainer: { sig: 'SoupStrainer(name=None, attrs={}, **kwargs)', doc: 'Limit parsing to matching tags.', kind: 'class' },
            Tag:        { sig: 'Tag',                                  doc: 'A single HTML/XML element.', kind: 'class' },
            NavigableString: { sig: 'NavigableString',                 doc: 'A string inside a Tag.', kind: 'class' },
            Comment:    { sig: 'Comment',                              doc: 'An HTML comment.', kind: 'class' },
        },

        // ── click ───────────────────────────────────────────────────────────
        click: {
            command:    { sig: 'command(name=None, **kwargs)',         doc: 'Decorator: declare a CLI command.\n```python\n@click.command()\n@click.option("--name")\ndef hi(name): pass\n```' },
            group:      { sig: 'group(name=None, **kwargs)',           doc: 'Decorator: declare a command group.' },
            option:     { sig: 'option(*param_decls, **attrs)',        doc: 'Decorator: declare an option.' },
            argument:   { sig: 'argument(*param_decls, **attrs)',      doc: 'Decorator: declare a positional argument.' },
            echo:       { sig: 'echo(message=None, file=None, nl=True, err=False, color=None)', doc: 'Print to stdout/stderr.' },
            secho:      { sig: 'secho(message=None, fg=None, bg=None, bold=None, **kw)', doc: 'echo with style.' },
            style:      { sig: 'style(text, fg=None, bg=None, bold=None)', doc: 'Apply ANSI styling to text.' },
            prompt:     { sig: 'prompt(text, default=None, hide_input=False, type=None)', doc: 'Prompt user for input.' },
            confirm:    { sig: 'confirm(text, default=False, abort=False)', doc: 'Yes/no prompt.' },
            Path:       { sig: 'Path(exists=False, file_okay=True, dir_okay=True)', doc: 'Path-typed parameter.', kind: 'class' },
            Choice:     { sig: 'Choice(choices, case_sensitive=True)', doc: 'Enum-typed parameter.', kind: 'class' },
            File:       { sig: 'File(mode="r", encoding=None, lazy=None)', doc: 'File-typed parameter.', kind: 'class' },
        },

        // ── yaml (PyYAML) ───────────────────────────────────────────────────
        yaml: {
            safe_load:  { sig: 'safe_load(stream)',                    doc: 'Parse a YAML document safely.' },
            safe_dump:  { sig: 'safe_dump(data, stream=None, **kwargs)', doc: 'Serialize to YAML safely.' },
            load:       { sig: 'load(stream, Loader)',                 doc: 'Parse YAML — REQUIRES Loader. Use safe_load instead.' },
            dump:       { sig: 'dump(data, stream=None, Dumper=Dumper, **kw)', doc: 'Serialize to YAML.' },
            safe_load_all: { sig: 'safe_load_all(stream)',             doc: 'Parse multi-doc YAML.' },
            YAMLError:  { sig: 'YAMLError',                            doc: 'Base YAML parsing exception.', kind: 'class' },
            SafeLoader: { sig: 'SafeLoader',                           doc: 'Restricted Loader (no arbitrary objects).', kind: 'class' },
            FullLoader: { sig: 'FullLoader',                           doc: 'Full Loader (arbitrary classes).', kind: 'class' },
        },

        // ── jinja2 ──────────────────────────────────────────────────────────
        jinja2: {
            Environment:  { sig: 'Environment(loader=None, autoescape=False, **kwargs)', doc: 'Template engine + config.', kind: 'class' },
            Template:     { sig: 'Template(source, **kwargs)',        doc: 'Compile + render a single template.\n```python\nTemplate("Hi {{ name }}").render(name="A")\n```', kind: 'class' },
            FileSystemLoader: { sig: 'FileSystemLoader(searchpath, encoding="utf-8")', doc: 'Load templates from disk.', kind: 'class' },
            DictLoader:   { sig: 'DictLoader({"name": "source"})',    doc: 'Load templates from dict.', kind: 'class' },
            select_autoescape: { sig: 'select_autoescape(enabled_extensions=("html","htm","xml"))', doc: 'Per-extension autoescape policy.' },
            Markup:       { sig: 'Markup(s)',                         doc: 'String marked safe (no escaping).', kind: 'class' },
        },

        // ── fsspec ──────────────────────────────────────────────────────────
        fsspec: {
            open:         { sig: 'open(urlpath, mode="rb", **kwargs)', doc: 'Open a file at a URL (local, http, …).\n```python\nwith fsspec.open("file:///tmp/x.txt") as f: ...\n```' },
            open_files:   { sig: 'open_files(urlpath, mode="rb", **kwargs)', doc: 'Open multiple files matching a glob.' },
            filesystem:   { sig: 'filesystem(protocol, **storage_options)', doc: 'Get a filesystem instance for protocol.' },
            get_filesystem_class: { sig: 'get_filesystem_class(protocol)', doc: 'Class for a registered protocol.' },
            url_to_fs:    { sig: 'url_to_fs(url, **kwargs)',          doc: '(filesystem, path) tuple from a URL.' },
            available_protocols: { sig: 'available_protocols()',      doc: 'List installed protocol names.' },
        },

        // ── webview (pywebview shim) ────────────────────────────────────────
        webview: {
            create_window: { sig: 'create_window(title, url=None, html=None, **kw)', doc: 'CodeBench shim — routes window contents to in-app preview pane.' },
            start:         { sig: 'start(func=None, args=(), debug=False, **kw)', doc: 'No-op on iOS — windows are created lazily.' },
        },
    };

    // Module-name aliases — these map top-level names to their full module key
    const MOD_KEY_ALIASES = {
        'np': 'numpy',
        'plt': 'matplotlib.pyplot',
        'mpl': 'matplotlib',
        'sp': 'scipy',
        'sym': 'sympy',
        'pd': 'pandas',
        'nx': 'networkx',
        'hf': 'huggingface_hub',
        'pywebview': 'webview',
    };

    function libSymbolsFor(qualifier) {
        const key = MOD_KEY_ALIASES[qualifier] || qualifier;
        // Merge: hardcoded LIB_SYMBOLS (rich docs) + runtime-introspected
        // names from window.__pythonSymbolIndex (covers everything actually
        // installed, no docs but at least all real attributes appear).
        const hard = LIB_SYMBOLS[key] || null;
        const rt = (window.__pythonSymbolIndex
                    && window.__pythonSymbolIndex.modules
                    && window.__pythonSymbolIndex.modules[key]) || null;
        if (!hard && !rt) return null;
        if (!rt) return hard;
        // Build a merged map. Hard entries win on conflict (richer docs).
        const out = {};
        for (const n in rt) {
            const k = rt[n];
            const kindStr =
                k === 5 || k === 6 ? 'class' :
                k === 8            ? 'mod'   :
                k === 4 || k === 13? 'var'   :
                k === 14           ? 'const' :
                                     'fn';
            out[n] = { sig: n, doc: '(introspected from ' + key + ')', kind: kindStr };
        }
        if (hard) for (const n in hard) out[n] = hard[n];
        return out;
    }

    function kindFromLibSpec(spec) {
        if (!spec || !spec.kind) return K.Function;
        switch (spec.kind) {
            case 'class': return K.Class;
            case 'const': return K.Constant;
            case 'mod':   return K.Module;
            case 'var':   return K.Variable;
            default:      return K.Function;
        }
    }

    // Build completion items for members of a library (instant, no round-trip)
    function libMemberCompletions(qualifier, range) {
        const members = libSymbolsFor(qualifier);
        if (!members) return [];
        const results = [];
        for (const name in members) {
            const spec = members[name];
            const kind = kindFromLibSpec(spec);
            const isCallable = kind === K.Function || kind === K.Class || kind === K.Method || kind === K.Constructor;
            results.push({
                label: name,
                kind: kind,
                range,
                insertText: isCallable ? name + '(${0})' : name,
                insertTextRules: SNIP,
                detail: spec.sig,
                documentation: spec.doc ? { value: spec.doc } : '',
                sortText: '3_' + name,
            });
        }
        return results;
    }

    // ═════════════════════════════════════════════════════════════════════════
    // SIGNATURE HELP DATABASE (builtins + library functions)
    // ═════════════════════════════════════════════════════════════════════════
    const SIG_DB = {
        print: [{
            label: 'print(*values, sep=" ", end="\\n", file=sys.stdout, flush=False) -> None',
            doc: '**print** → None\n\nPrint to a stream.',
            params: [
                p('*values',            '**values** — any objects to print.'),
                p('sep=" "',            '**sep** `str` — string between values.'),
                p('end="\\n"',          '**end** `str` — string after final value.'),
                p('file=sys.stdout',    '**file** — file-like to write to.'),
                p('flush=False',        '**flush** `bool` — force-flush the stream.'),
            ],
        }],
        range: [
            { label: 'range(stop: int) -> range',
              doc: '**range(stop)** — 0, 1, …, stop-1.',
              params: [p('stop: int', '**stop** — upper bound (exclusive).')],
            },
            { label: 'range(start: int, stop: int, step: int = 1) -> range',
              doc: '**range(start, stop, step)** — sequence start, start+step, … < stop.',
              params: [
                  p('start: int',    '**start** — first value.'),
                  p('stop: int',     '**stop** — upper bound (exclusive).'),
                  p('step: int = 1', '**step** — increment (can be negative).'),
              ],
            },
        ],
        len: [{ label: 'len(obj) -> int', doc: 'Number of items.', params: [p('obj', 'Any container.')] }],
        open: [{
            label: 'open(file, mode="r", encoding=None, newline=None, errors=None, buffering=-1)',
            doc: 'Open a file.',
            params: [
                p('file',          '**file** — path or file descriptor.'),
                p('mode="r"',      '**mode** — "r"/"w"/"a"/"x" + "b"/"t" + "+".'),
                p('encoding=None', '**encoding** — e.g. "utf-8".'),
                p('newline=None',  '**newline** — how to handle line endings.'),
                p('errors=None',   '**errors** — error handler name.'),
                p('buffering=-1',  '**buffering** — buffer policy.'),
            ],
        }],
        enumerate: [{
            label: 'enumerate(iterable, start=0) -> Iterator[tuple[int, T]]',
            doc: 'Yield (index, value) pairs.',
            params: [p('iterable', 'Any iterable.'), p('start=0', 'First index.')],
        }],
        zip: [{
            label: 'zip(*iterables, strict=False) -> Iterator[tuple]',
            doc: 'Pair up elements.',
            params: [p('*iterables', 'Two or more iterables.'), p('strict=False', 'Raise on length mismatch (3.10+).')],
        }],
        sorted: [{
            label: 'sorted(iterable, /, *, key=None, reverse=False) -> list',
            doc: 'New sorted list.',
            params: [
                p('iterable',        'Items to sort.'),
                p('key=None',        'Function producing comparison key.'),
                p('reverse=False',   'Descending if True.'),
            ],
        }],
        isinstance: [{
            label: 'isinstance(obj, classinfo) -> bool',
            doc: 'Type membership check.',
            params: [p('obj', 'Any.'), p('classinfo', 'class or tuple of classes.')],
        }],
        map: [{
            label: 'map(function, *iterables) -> Iterator',
            doc: 'Apply function to each element.',
            params: [p('function', 'Callable applied to each item.'), p('*iterables', 'One or more.')],
        }],
        filter: [{
            label: 'filter(function, iterable) -> Iterator',
            doc: 'Keep items where function(item) is truthy.',
            params: [p('function', 'Callable or None.'), p('iterable', 'Sequence.')],
        }],
        input: [{
            label: 'input(prompt="") -> str',
            doc: 'Read a line from stdin.',
            params: [p('prompt=""', 'Prompt shown before reading.')],
        }],
        getattr: [{
            label: 'getattr(obj, name, default=MISSING) -> Any',
            doc: 'Get attribute from obj.',
            params: [p('obj', 'Target.'), p('name', 'Attribute name.'), p('default', 'Returned if missing.')],
        }],
        setattr: [{
            label: 'setattr(obj, name, value) -> None',
            doc: 'Set attribute on obj.',
            params: [p('obj', 'Target.'), p('name', 'Attribute name.'), p('value', 'New value.')],
        }],
        hasattr: [{
            label: 'hasattr(obj, name) -> bool',
            doc: 'Does obj have attribute?',
            params: [p('obj', 'Target.'), p('name', 'Attribute name.')],
        }],
        round: [{
            label: 'round(number, ndigits=None) -> number',
            doc: 'Round to ndigits (default: nearest int).',
            params: [p('number', 'Value.'), p('ndigits=None', 'Decimal places.')],
        }],
        pow: [{
            label: 'pow(base, exp, mod=None) -> number',
            doc: 'Exponentiation.',
            params: [p('base', 'Base.'), p('exp', 'Exponent.'), p('mod=None', 'Modulus (if given, computes (base**exp) % mod efficiently).')],
        }],
        sum: [{
            label: 'sum(iterable, /, start=0) -> number',
            doc: 'Sum all items.',
            params: [p('iterable', 'Sequence of numbers.'), p('start=0', 'Initial value.')],
        }],
        max: [{
            label: 'max(iterable, *, key=None, default=MISSING) -> Any',
            doc: 'Maximum item.',
            params: [p('iterable', 'Items.'), p('key=None', 'Key function.'), p('default', 'Returned if empty.')],
        }],
        min: [{
            label: 'min(iterable, *, key=None, default=MISSING) -> Any',
            doc: 'Minimum item.',
            params: [p('iterable', 'Items.'), p('key=None', 'Key function.'), p('default', 'Returned if empty.')],
        }],
    };

    // Flatten library signatures into SIG_DB too, keyed by bare function name
    for (const modKey in LIB_SYMBOLS) {
        const members = LIB_SYMBOLS[modKey];
        for (const name in members) {
            const spec = members[name];
            if (!spec.sig) continue;
            if (SIG_DB[name]) continue; // don't overwrite builtins
            // Extract params from signature like "func(a, b=1, c=None)"
            const m = spec.sig.match(/^(?:[\w\.]+\.)?(\w+)\(([\s\S]*)\)(?:\s*->\s*.+)?$/);
            if (!m) continue;
            const params = m[2].split(/,(?![^(]*\))/)
                .map(s => s.trim())
                .filter(Boolean)
                .map(s => p(s, '**' + s + '**'));
            SIG_DB[name] = [{ label: spec.sig, doc: spec.doc || '', params }];
        }
    }

    // ═════════════════════════════════════════════════════════════════════════
    // LOCAL-SCOPE SCANNER — picks up user-defined names so completions
    // include local variables, functions, classes, loop vars, import aliases.
    // Mirrors what Pylance does statically (VS Code's Python IntelliSense).
    // ═════════════════════════════════════════════════════════════════════════
    function scanLocalScope(text, beforeLine) {
        // Kinds: 6 var, 3 func, 7 class, 5 field (self.foo), 9 module, 12 iterable
        const locals = {}; // name -> { kind, detail }
        const add = (name, kind, detail) => {
            if (!name || !/^[A-Za-z_]\w*$/.test(name)) return;
            if (PYTHON_BUILTIN_SET.has(name)) return;
            if (PYTHON_KEYWORD_SET.has(name)) return;
            if (!locals[name] || rank(kind) < rank(locals[name].kind)) {
                locals[name] = { kind, detail: detail || '' };
            }
        };
        const rank = (k) => ({ 7: 0, 3: 1, 12: 2, 6: 3, 9: 4, 5: 5 }[k] ?? 9);

        const lines = text.split('\n');
        const limit = Math.min(lines.length, beforeLine != null ? beforeLine : lines.length);
        for (let i = 0; i < limit; i++) {
            const line = lines[i];
            if (!line || line.trimStart().startsWith('#')) continue;
            let m;
            // class Name(...):
            if ((m = line.match(/^\s*class\s+(\w+)/))) add(m[1], 7, 'class');
            // def name(args):  → record function AND its args
            if ((m = line.match(/^\s*(?:async\s+)?def\s+(\w+)\s*\(([^)]*)\)/))) {
                add(m[1], 3, 'function');
                for (const raw of m[2].split(',')) {
                    const name = raw.trim().split(/[:=]/)[0].replace(/^\*+/, '').trim();
                    if (name && name !== 'self' && name !== 'cls') add(name, 6, 'param');
                }
            }
            // for x, y in ... :
            if ((m = line.match(/^\s*for\s+([\w,\s*()]+)\s+in\s+/))) {
                const names = m[1].replace(/[()]/g, '').split(',').map(s => s.trim().replace(/^\*+/, ''));
                for (const n of names) add(n, 6, 'loop var');
            }
            // with expr as name:
            if ((m = line.match(/\bas\s+(\w+)\s*[:)]/))) add(m[1], 6, 'context');
            // simple assignment: name = ... (but not inside string/f-string; good-enough regex)
            const assignRe = /^\s*([A-Za-z_]\w*)\s*(?::\s*[\w\[\], ]+)?\s*=(?!=)/;
            if ((m = line.match(assignRe))) {
                // Infer a loose kind from RHS
                const rhs = line.slice(m.index + m[0].length).trim();
                let kind = 6;
                let detail = 'variable';
                if (/^(?:\[|list\()/.test(rhs))   { kind = 12; detail = 'list'; }
                else if (/^\{.*:.*\}|^dict\(/.test(rhs)) { kind = 12; detail = 'dict'; }
                else if (/^\(|^tuple\(/.test(rhs))       { kind = 12; detail = 'tuple'; }
                else if (/^\{.*\}|^set\(/.test(rhs))     { kind = 12; detail = 'set'; }
                else if (/^lambda\b/.test(rhs))          { kind = 3;  detail = 'lambda'; }
                else if (/^\w+\(.*\)$/.test(rhs))        { kind = 6;  detail = 'instance'; }
                add(m[1], kind, detail);
            }
            // Multi-assign: a, b = 1, 2
            const multiRe = /^\s*([\w,\s]+?)\s*=(?!=)/;
            if ((m = line.match(multiRe)) && m[1].includes(',')) {
                for (const n of m[1].split(',')) add(n.trim(), 6, 'variable');
            }
            // self.x = ...
            if ((m = line.match(/^\s*self\.(\w+)\s*=/))) add(m[1], 5, 'self');
        }
        return locals;
    }

    // Lookup sets for fast filtering in scanLocalScope
    const PYTHON_KEYWORD_SET = new Set([
        'def','class','import','from','if','elif','else','for','while','try',
        'except','finally','with','as','return','yield','lambda','async','await',
        'pass','break','continue','raise','del','global','nonlocal','not','and',
        'or','in','is','True','False','None','assert',
    ]);
    const PYTHON_BUILTIN_SET = new Set([
        'print','len','range','list','dict','set','tuple','str','int','float',
        'bool','bytes','type','isinstance','issubclass','hasattr','getattr',
        'setattr','enumerate','zip','map','filter','sorted','reversed','sum',
        'min','max','abs','round','pow','open','input','super','property','all',
        'any','iter','next','hash','id','repr','format','callable','chr','ord',
        'hex','oct','bin','slice','eval','exec','compile','globals','locals',
        'help','object','self','cls',
    ]);

    // ═════════════════════════════════════════════════════════════════════════
    // CONTEXT-AWARE COMPLETION PROVIDER
    // Detects where the cursor is (member access, `for X `, `for X in `,
    // `if`/`while`/`return`, decorator, import, default) and returns a
    // TARGETED list — mimics VS Code / Pylance behavior as closely as possible
    // without a real language server.
    // ═════════════════════════════════════════════════════════════════════════
    monaco.languages.registerCompletionItemProvider('python', {
        // Broad trigger so the widget re-queries aggressively
        triggerCharacters: ['.', ' ', '(', ',', '=', ':', '@', '_', '[', '"', "'"],
        provideCompletionItems(model, position) {
            const range = mkRange(model, position);
            const prefix = linePrefix(model, position);
            const fullText = model.getValue();
            const parsed = parseImports(fullText);
            const locals = scanLocalScope(fullText, position.lineNumber);

            // Helper: build completion items for every local name
            const localItems = () => {
                const out = [];
                for (const name in locals) {
                    const info = locals[name];
                    const isCallable = info.kind === 3 || info.kind === 7;
                    out.push({
                        label: name,
                        kind: mapKind(info.kind),
                        range,
                        insertText: isCallable ? name + '(${0})' : name,
                        insertTextRules: SNIP,
                        detail: info.detail,
                        sortText: '1_' + name, // locals rank very high
                    });
                }
                return out;
            };

            // Common iterable producers — the list VS Code shows after `for x in `
            const iterableProducers = () => [
                { label: 'range', kind: K.Function, range, insertText: 'range(${1:n})', insertTextRules: SNIP,
                  detail: 'range(stop) or range(start, stop, step)', documentation: { value: 'Arithmetic progression `0, 1, 2, …, n-1`.' }, sortText: '0_range' },
                { label: 'enumerate', kind: K.Function, range, insertText: 'enumerate(${1:iterable})', insertTextRules: SNIP,
                  detail: 'enumerate(iterable, start=0)', documentation: { value: 'Yield `(index, value)` pairs.' }, sortText: '0_enumerate' },
                { label: 'zip', kind: K.Function, range, insertText: 'zip(${1:a}, ${2:b})', insertTextRules: SNIP,
                  detail: 'zip(*iterables, strict=False)', documentation: { value: 'Pair up elements from multiple iterables.' }, sortText: '0_zip' },
                { label: 'reversed', kind: K.Function, range, insertText: 'reversed(${1:seq})', insertTextRules: SNIP,
                  detail: 'reversed(seq)', documentation: { value: 'Reverse iterator.' }, sortText: '0_reversed' },
                { label: 'sorted', kind: K.Function, range, insertText: 'sorted(${1:iterable})', insertTextRules: SNIP,
                  detail: 'sorted(iterable, *, key=None, reverse=False)', documentation: { value: 'New sorted list.' }, sortText: '0_sorted' },
                { label: 'map', kind: K.Function, range, insertText: 'map(${1:func}, ${2:iterable})', insertTextRules: SNIP,
                  detail: 'map(func, *iterables)', sortText: '0_map' },
                { label: 'filter', kind: K.Function, range, insertText: 'filter(${1:func}, ${2:iterable})', insertTextRules: SNIP,
                  detail: 'filter(func, iterable)', sortText: '0_filter' },
                { label: 'iter', kind: K.Function, range, insertText: 'iter(${1:obj})', insertTextRules: SNIP,
                  detail: 'iter(obj[, sentinel])', sortText: '0_iter' },
            ];

            // ═══ CONTEXT 1: Decorator line `@|` or `@ foo` ═══
            if (/^\s*@\w*$/.test(prefix)) {
                return { suggestions: [
                    { label: 'staticmethod',    kind: K.Snippet, range, insertText: 'staticmethod',    detail: 'Mark method static (no self/cls).', sortText: '0_staticmethod' },
                    { label: 'classmethod',     kind: K.Snippet, range, insertText: 'classmethod',     detail: 'Pass class as first arg.', sortText: '0_classmethod' },
                    { label: 'property',        kind: K.Snippet, range, insertText: 'property',        detail: 'Getter decorator.', sortText: '0_property' },
                    { label: 'dataclass',       kind: K.Snippet, range, insertText: 'dataclass',       detail: '@dataclass from dataclasses.', sortText: '0_dataclass' },
                    { label: 'cached_property', kind: K.Snippet, range, insertText: 'cached_property', detail: 'functools.cached_property', sortText: '0_cached_property' },
                    { label: 'lru_cache',       kind: K.Snippet, range, insertText: 'lru_cache(maxsize=${1:128})', insertTextRules: SNIP, detail: 'functools.lru_cache', sortText: '0_lru_cache' },
                    { label: 'wraps',           kind: K.Snippet, range, insertText: 'wraps(${1:wrapped})', insertTextRules: SNIP, detail: 'functools.wraps', sortText: '0_wraps' },
                ]};
            }

            // ═══ CONTEXT 2: `X.` member access (library + daemon + self.* for classes) ═══
            const memberMatch = prefix.match(/(\w+)\.\s*$/) || prefix.match(/(\w+)\.$/);
            if (memberMatch) {
                const qualifier = memberMatch[1];
                const resolved = resolveAlias(qualifier, parsed);

                let items = libMemberCompletions(qualifier, range);
                if (items.length === 0) items = libMemberCompletions(resolved, range);

                const idx = window.__pythonSymbolIndex;
                if (idx && idx.modules) {
                    const modMap = idx.modules[resolved] || idx.modules[qualifier];
                    if (modMap) {
                        const known = new Set(items.map(i => i.label));
                        for (const name in modMap) {
                            if (known.has(name)) continue;
                            const rawKind = modMap[name];
                            items.push({
                                label: name,
                                kind: mapKind(rawKind),
                                range,
                                insertText: (rawKind === 3 || rawKind === 2 || rawKind === 4 || rawKind === 7)
                                    ? name + '(${0})' : name,
                                insertTextRules: SNIP,
                                detail: resolved,
                                sortText: '4_' + name,
                                __resolveQualifier: resolved,
                            });
                        }
                    }
                }
                if (items.length > 0) return { suggestions: items };
                // fall through to default list
            }

            // ═══ CONTEXT 3: `for <name> ` (space after loop variable) → suggest `in` ═══
            // e.g. user typed "for i " — insert "in "
            if (/^\s*for\s+[\w,\s*()]+\s$/.test(prefix) && !/\bin\s*$/.test(prefix)) {
                return { suggestions: [{
                    label: 'in',
                    kind: K.Keyword,
                    range,
                    insertText: 'in ',
                    detail: 'for-loop keyword',
                    documentation: { value: 'Use after the loop variable: `for i in <iterable>:`.' },
                    sortText: '0_in',
                    preselect: true,
                }]};
            }

            // ═══ CONTEXT 4: `for <name> in ` → suggest range/enumerate/zip + local iterables ═══
            if (/^\s*for\s+[\w,\s*()]+\s+in\s+\w*$/.test(prefix)) {
                const items = iterableProducers();
                // Prefer local variables that look like iterables
                for (const name in locals) {
                    const info = locals[name];
                    if (info.kind === 12 /* Value ~ iterable */ || info.detail === 'param') {
                        items.push({
                            label: name, kind: K.Variable, range,
                            insertText: name, detail: info.detail || 'iterable',
                            sortText: '1_' + name,
                        });
                    }
                }
                return { suggestions: items };
            }

            // ═══ CONTEXT 5: `while ` / `if ` / `elif ` / `return ` / `yield ` ═══
            if (/^\s*(while|if|elif|return|yield|raise|assert|not)\s+\w*$/.test(prefix)) {
                const items = [];
                // Locals (variables + functions)
                for (const name in locals) {
                    const info = locals[name];
                    const isCallable = info.kind === 3 || info.kind === 7;
                    items.push({
                        label: name, kind: mapKind(info.kind), range,
                        insertText: isCallable ? name + '(${0})' : name,
                        insertTextRules: SNIP,
                        detail: info.detail, sortText: '1_' + name,
                    });
                }
                // Boolean literals / common conditions
                const kw = prefix.match(/^\s*(\w+)\s/)?.[1] || '';
                if (kw === 'return' || kw === 'yield') {
                    items.push({ label: 'None', kind: K.Constant, range, insertText: 'None', sortText: '0_None' });
                    items.push({ label: 'self', kind: K.Variable, range, insertText: 'self', sortText: '0_self' });
                }
                if (kw === 'if' || kw === 'elif' || kw === 'while' || kw === 'assert' || kw === 'not') {
                    items.push({ label: 'True',  kind: K.Constant, range, insertText: 'True',  sortText: '0_True' });
                    items.push({ label: 'False', kind: K.Constant, range, insertText: 'False', sortText: '0_False' });
                    items.push({ label: 'None',  kind: K.Constant, range, insertText: 'None',  sortText: '0_None' });
                    items.push({ label: 'isinstance', kind: K.Function, range,
                                 insertText: 'isinstance(${1:obj}, ${2:type})', insertTextRules: SNIP,
                                 detail: 'isinstance(obj, classinfo) -> bool', sortText: '0_isinstance' });
                    items.push({ label: 'len', kind: K.Function, range,
                                 insertText: 'len(${1:obj})', insertTextRules: SNIP,
                                 detail: 'len(obj) -> int', sortText: '0_len' });
                }
                if (kw === 'raise') {
                    for (const exc of ['Exception','ValueError','TypeError','KeyError','IndexError','RuntimeError','AttributeError','NotImplementedError','StopIteration','FileNotFoundError','ZeroDivisionError']) {
                        items.push({ label: exc, kind: K.Class, range,
                                     insertText: exc + '(${1:"message"})', insertTextRules: SNIP,
                                     detail: 'built-in exception', sortText: '0_' + exc });
                    }
                }
                return { suggestions: items };
            }

            // ═══ CONTEXT 6: `from X import ` — module members ═══
            const fromMatch = prefix.match(/\bfrom\s+([\w\.]+)\s+import\s+[\w,\s]*$/);
            if (fromMatch) {
                const mod = fromMatch[1];
                let items = libMemberCompletions(mod, range);
                const idx = window.__pythonSymbolIndex;
                if (idx?.modules?.[mod]) {
                    const known = new Set(items.map(i => i.label));
                    for (const name in idx.modules[mod]) {
                        if (known.has(name)) continue;
                        items.push({ label: name, kind: mapKind(idx.modules[mod][name]), range, insertText: name, sortText: '4_' + name });
                    }
                }
                return { suggestions: items };
            }

            // ═══ CONTEXT 7: `import X` / `from X` — module names ═══
            if (/\b(?:import|from)\s+\w*$/.test(prefix)) {
                return { suggestions: moduleNames(range) };
            }

            // ═══ CONTEXT 8 (default): keywords + builtins + locals + snippets + aliases ═══
            // Statement-only items (import snippets, `def`, `class`, `from`…) are
            // filtered out unless the cursor is at the START of a line. This
            // matches VS Code / Pylance — you don't see "import numpy" as a
            // suggestion inside `x = foo(|)`.
            const atLineStart = isAtLineStart(model, position);
            const filteredKw = kwItems(range).filter(k => {
                if (STATEMENT_KEYWORDS.has(k.label) && !atLineStart) return false;
                return true;
            });
            const suggestions = [
                ...filteredKw,
                ...builtinItems(range),
                ...(atLineStart ? importSnippets(range) : []),
                ...localItems(),
            ];
            for (const mod of parsed.wildcard) {
                suggestions.push(...libMemberCompletions(mod, range));
                const idx = window.__pythonSymbolIndex;
                if (idx?.modules?.[mod]) {
                    for (const name in idx.modules[mod]) {
                        suggestions.push({
                            label: name, kind: mapKind(idx.modules[mod][name]), range,
                            insertText: name, detail: mod, sortText: '4_' + name,
                        });
                    }
                }
            }
            for (const sym in parsed.fromSymbols) {
                suggestions.push({
                    label: sym, kind: K.Function, range,
                    insertText: sym + '(${0})', insertTextRules: SNIP,
                    detail: parsed.fromSymbols[sym], sortText: '3_' + sym,
                });
            }
            for (const alias in parsed.aliases) {
                suggestions.push({
                    label: alias, kind: K.Module, range, insertText: alias,
                    detail: parsed.aliases[alias], sortText: '4_' + alias,
                });
            }
            for (const alias in DEFAULT_ALIASES) {
                if (!parsed.aliases[alias]) {
                    suggestions.push({
                        label: alias, kind: K.Module, range, insertText: alias,
                        detail: '→ ' + DEFAULT_ALIASES[alias],
                        sortText: '5_' + alias,
                    });
                }
            }
            return { suggestions };
        },

        resolveCompletionItem(item) {
            if (!item.__resolveQualifier) return item;
            return new Promise(resolve => {
                const id = 'rsv_' + Math.random().toString(36).slice(2);
                window.__resolvePending[id] = (result) => {
                    if (result.documentation) item.documentation = { value: result.documentation };
                    if (result.signature) item.detail = item.label + result.signature;
                    resolve(item);
                };
                postToSwift({ kind: 'resolveRequest', id, qualifier: item.__resolveQualifier, name: item.label });
                setTimeout(() => {
                    if (window.__resolvePending[id]) { delete window.__resolvePending[id]; resolve(item); }
                }, 1000);
            });
        },
    });

    function mapKind(raw) {
        const M = {
            1: K.Text, 2: K.Method, 3: K.Function, 4: K.Constructor, 5: K.Field,
            6: K.Variable, 7: K.Class, 8: K.Interface, 9: K.Module, 10: K.Property,
            11: K.Unit, 12: K.Value, 13: K.Enum, 14: K.Keyword, 15: K.Snippet,
            16: K.Color, 17: K.File, 18: K.Reference, 19: K.Folder, 20: K.EnumMember,
            21: K.Constant, 22: K.Struct, 23: K.Event, 24: K.Operator, 25: K.TypeParameter,
        };
        return M[raw] !== undefined ? M[raw] : K.Variable;
    }

    function moduleNames(range) {
        const results = [];
        const seen = new Set();
        for (const modName in LIB_SYMBOLS) {
            results.push({ label: modName, kind: K.Module, range, insertText: modName, sortText: '3_' + modName });
            seen.add(modName);
        }
        const idx = window.__pythonSymbolIndex;
        if (idx?.modules) {
            for (const modName in idx.modules) {
                if (seen.has(modName)) continue;
                results.push({ label: modName, kind: K.Module, range, insertText: modName, sortText: '4_' + modName });
            }
        }
        for (const alias in DEFAULT_ALIASES) {
            results.push({ label: alias, kind: K.Module, range, insertText: alias, detail: '→ ' + DEFAULT_ALIASES[alias], sortText: '5_' + alias });
        }
        return results;
    }

    // ═════════════════════════════════════════════════════════════════════════
    // SIGNATURE HELP PROVIDER
    // ═════════════════════════════════════════════════════════════════════════
    function getCallInfo(model, position) {
        const lineContent = model.getLineContent(position.lineNumber);
        const col = position.column - 1;
        let depth = 0;
        let i = col - 1;
        let activeParam = 0;
        while (i >= 0) {
            const ch = lineContent[i];
            if (ch === ')' || ch === ']' || ch === '}') depth++;
            else if (ch === '(' || ch === '[' || ch === '{') {
                if (depth === 0 && ch === '(') {
                    let j = i - 1;
                    while (j >= 0 && /[\w.]/.test(lineContent[j])) j--;
                    const fnName = lineContent.slice(j + 1, i).split('.').pop();
                    return { fnName, activeParam };
                }
                depth--;
            } else if (ch === ',' && depth === 0) {
                activeParam++;
            }
            i--;
        }
        return null;
    }

    monaco.languages.registerSignatureHelpProvider('python', {
        signatureHelpTriggerCharacters:   ['(', ','],
        signatureHelpRetriggerCharacters: [','],
        provideSignatureHelp(model, position) {
            const info = getCallInfo(model, position);
            if (!info || !info.fnName) return null;

            const sigs = SIG_DB[info.fnName];
            if (sigs && sigs.length > 0) {
                let sigIdx = sigs.length - 1;
                for (let i = 0; i < sigs.length; i++) {
                    if (sigs[i].params.length > info.activeParam) { sigIdx = i; break; }
                }
                const activeSig = sigs[sigIdx];
                return {
                    value: {
                        activeSignature: sigIdx,
                        activeParameter: Math.min(info.activeParam, activeSig.params.length - 1),
                        signatures: sigs.map(sig => ({
                            label: sig.label,
                            documentation: { value: sig.doc || '' },
                            parameters: sig.params.map(pp =>
                                typeof pp === 'string'
                                    ? { label: pp }
                                    : { label: pp.label, documentation: pp.doc ? { value: pp.doc } : undefined }
                            ),
                        })),
                    },
                    dispose() {},
                };
            }

            // Fall back to Swift daemon for unknown library functions
            return new Promise(resolve => {
                const id = 'sig_' + Math.random().toString(36).slice(2);
                window.__resolvePending[id] = (result) => {
                    if (!result.signature) { resolve(null); return; }
                    resolve({
                        value: {
                            activeSignature: 0,
                            activeParameter: info.activeParam,
                            signatures: [{
                                label: info.fnName + result.signature,
                                documentation: { value: result.documentation || '' },
                                parameters: [],
                            }],
                        },
                        dispose() {},
                    });
                };
                const fullText = model.getValue();
                const parsed = parseImports(fullText);
                let qualifier = 'builtins';
                for (const q of [...Object.keys(parsed.aliases), ...Object.keys(DEFAULT_ALIASES)]) {
                    const mod = resolveAlias(q, parsed);
                    if (window.__pythonSymbolIndex?.modules?.[mod]?.[info.fnName] !== undefined) {
                        qualifier = mod; break;
                    }
                }
                postToSwift({ kind: 'resolveRequest', id, qualifier, name: info.fnName });
                setTimeout(() => {
                    if (window.__resolvePending[id]) { delete window.__resolvePending[id]; resolve(null); }
                }, 800);
            });
        },
    });

    // ═════════════════════════════════════════════════════════════════════════
    // HOVER PROVIDER — static docs + library lookup
    // ═════════════════════════════════════════════════════════════════════════
    const HOVER_DOCS = {
        // Builtins
        print:      '**print(\\*values, sep=" ", end="\\n")** → None\n\nPrint objects to stdout.',
        len:        '**len(obj)** → int\n\nNumber of items in a container.',
        range:      '**range(start, stop[, step])** → range\n\nArithmetic progression iterator.',
        isinstance: '**isinstance(obj, classinfo)** → bool\n\nType membership check.',
        issubclass: '**issubclass(cls, classinfo)** → bool',
        open:       '**open(file, mode="r")** → file\n\nOpen a file for reading/writing.',
        enumerate:  '**enumerate(iterable, start=0)** → Iterator[tuple]\n\nYields (index, value) pairs.',
        zip:        '**zip(\\*iterables)** → Iterator[tuple]\n\nAggregate elements from each iterable.',
        map:        '**map(func, \\*iterables)** → Iterator\n\nApply func to each item.',
        filter:     '**filter(func, iterable)** → Iterator\n\nKeep items where func(item) is truthy.',
        sorted:     '**sorted(iterable, \\*, key, reverse)** → list\n\nReturn a new sorted list.',
        reversed:   '**reversed(seq)** → iterator\n\nReturn reverse iterator.',
        sum:        '**sum(iterable, /, start=0)** → number\n\nSum of elements.',
        min:        '**min(iterable, \\*, key, default)** → Any\n\nMinimum item.',
        max:        '**max(iterable, \\*, key, default)** → Any\n\nMaximum item.',
        abs:        '**abs(x)** → number\n\nAbsolute value.',
        round:      '**round(number, ndigits=None)** → number',
        pow:        '**pow(base, exp, mod=None)** → number',
        input:      '**input(prompt="")** → str\n\nRead a line from stdin.',
        type:       '**type(obj)** → type\n\nor **type(name, bases, dict)** → new class',
        hasattr:    '**hasattr(obj, name)** → bool',
        getattr:    '**getattr(obj, name[, default])** → Any',
        setattr:    '**setattr(obj, name, value)**',
        any:        '**any(iterable)** → bool',
        all:        '**all(iterable)** → bool',
        next:       '**next(iterator[, default])** → Any',
        iter:       '**iter(obj[, sentinel])** → iterator',
        hash:       '**hash(obj)** → int',
        id:         '**id(obj)** → int',
        repr:       '**repr(obj)** → str',
        callable:   '**callable(obj)** → bool',
        chr:        '**chr(i)** → str',
        ord:        '**ord(c)** → int',
        hex:        '**hex(x)** → str',
        oct:        '**oct(x)** → str',
        bin:        '**bin(x)** → str',
        // Keywords
        def:        '**def** — Define a function.',
        class:      '**class** — Define a class.',
        import:     '**import** — Import a module. `import X` or `from X import y`',
        from:       '**from** — `from module import name`',
        if:         '**if** — Conditional execution.',
        elif:       '**elif** — Else-if.',
        else:       '**else** — Else branch.',
        for:        '**for** — Iterate over an iterable.',
        while:      '**while** — Loop while condition is truthy.',
        try:        '**try** — Exception handling.',
        except:     '**except** — Catch an exception.',
        finally:    '**finally** — Always-executed cleanup.',
        with:       '**with** — Context manager.',
        return:     '**return** — Return from function.',
        yield:      '**yield** — Yield from generator.',
        lambda:     '**lambda args: expr** — Anonymous function.',
        async:      '**async** — Async function/generator/context manager.',
        await:      '**await** — Await coroutine.',
        True:       '**True** — boolean true constant.',
        False:      '**False** — boolean false constant.',
        None:       '**None** — null-like constant.',
        self:       '**self** — Reference to the current instance inside a method.',
        cls:        '**cls** — Reference to the class inside a classmethod.',
    };

    monaco.languages.registerHoverProvider('python', {
        provideHover(model, position) {
            const word = model.getWordAtPosition(position);
            if (!word) return null;

            // 1. Static hover docs
            const staticDoc = HOVER_DOCS[word.word];
            if (staticDoc) {
                return {
                    range: new monaco.Range(position.lineNumber, word.startColumn, position.lineNumber, word.endColumn),
                    contents: [{ value: staticDoc }],
                };
            }

            // 2. Is this a library member? Look back for `X.<word>` pattern
            const line = model.getLineContent(position.lineNumber);
            const before = line.slice(0, word.startColumn - 1);
            const memberMatch = before.match(/(\w+)\.\s*$/);
            if (memberMatch) {
                const qualifier = memberMatch[1];
                const members = libSymbolsFor(qualifier);
                if (members && members[word.word]) {
                    const spec = members[word.word];
                    const lines = [];
                    if (spec.sig) lines.push('```python\n' + qualifier + '.' + spec.sig + '\n```');
                    if (spec.doc) lines.push(spec.doc);
                    return {
                        range: new monaco.Range(position.lineNumber, word.startColumn, position.lineNumber, word.endColumn),
                        contents: [{ value: lines.join('\n\n') }],
                    };
                }
            }

            // 3. Bare name in library DB (from `from X import foo`)
            for (const modKey in LIB_SYMBOLS) {
                const spec = LIB_SYMBOLS[modKey][word.word];
                if (spec) {
                    const lines = [];
                    if (spec.sig) lines.push('```python\n' + word.word + ' (from ' + modKey + ')\n' + spec.sig + '\n```');
                    if (spec.doc) lines.push(spec.doc);
                    return {
                        range: new monaco.Range(position.lineNumber, word.startColumn, position.lineNumber, word.endColumn),
                        contents: [{ value: lines.join('\n\n') }],
                    };
                }
            }

            // 4. Progressive: ask Swift daemon
            const fullText = model.getValue();
            const parsed = parseImports(fullText);
            for (const q of [...Object.keys(parsed.aliases), ...Object.keys(DEFAULT_ALIASES)]) {
                const mod = resolveAlias(q, parsed);
                const members = window.__pythonSymbolIndex?.modules?.[mod];
                if (members && members[word.word] !== undefined) {
                    return new Promise(resolve => {
                        const id = 'hv_' + Math.random().toString(36).slice(2);
                        window.__resolvePending[id] = (result) => {
                            const lines = [];
                            if (result.signature) lines.push('**' + word.word + '**`' + result.signature + '`');
                            if (result.documentation) lines.push(result.documentation);
                            if (!lines.length) { resolve(null); return; }
                            resolve({
                                range: new monaco.Range(position.lineNumber, word.startColumn, position.lineNumber, word.endColumn),
                                contents: [{ value: lines.join('\n\n') }],
                            });
                        };
                        postToSwift({ kind: 'resolveRequest', id, qualifier: mod, name: word.word });
                        setTimeout(() => {
                            if (window.__resolvePending[id]) { delete window.__resolvePending[id]; resolve(null); }
                        }, 500);
                    });
                }
            }
            return null;
        },
    });

    console.log('[editor.js] Python providers registered — ' + Object.keys(SIG_DB).length + ' signatures, ' + Object.keys(LIB_SYMBOLS).length + ' libraries');
};
/**
 * OfflinAi — C / C++ / Fortran IntelliSense for Monaco.
 *
 * Covers:
 *   - Keywords & snippets (if/for/while/switch/struct/class/template/...)
 *   - Standard library functions with signatures (printf, malloc, std::sort, …)
 *   - Signature help tooltips on `(`
 *   - Hover docs for every symbol
 *   - Context-aware filtering so statement-only keywords (return, break, …)
 *     don't appear mid-expression.
 *
 * Call `window.registerCLanguages(monaco, editor)` after Monaco loads.
 */
window.registerCLanguages = function (monaco, editor) {
    const K    = monaco.languages.CompletionItemKind;
    const SNIP = monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet;
    const p    = (label, doc) => ({ label, doc });

    function mkRange(model, position) {
        const w = model.getWordUntilPosition(position);
        return {
            startLineNumber: position.lineNumber,
            endLineNumber:   position.lineNumber,
            startColumn:     w.startColumn,
            endColumn:       w.endColumn,
        };
    }
    function linePrefix(model, position) {
        const w = model.getWordUntilPosition(position);
        return model.getValueInRange({
            startLineNumber: position.lineNumber,
            startColumn: 1,
            endLineNumber: position.lineNumber,
            endColumn: w.startColumn,
        });
    }
    function isAtLineStart(model, position) {
        const w = model.getWordUntilPosition(position);
        const beforeWord = model.getValueInRange({
            startLineNumber: position.lineNumber, startColumn: 1,
            endLineNumber: position.lineNumber, endColumn: w.startColumn,
        });
        return /^\s*$/.test(beforeWord);
    }

    // ═════════════════════════════════════════════════════════════════════════
    // FORTRAN — register Monarch tokenizer (Monaco doesn't ship one)
    // ═════════════════════════════════════════════════════════════════════════
    (function registerFortranLang() {
        if (monaco.languages.getLanguages().some(l => l.id === 'fortran')) return;
        monaco.languages.register({ id: 'fortran', aliases: ['Fortran','fortran','f90','f95','f03','f08'], extensions: ['.f','.f90','.f95','.f03','.f08','.for','.F','.F90'] });
        monaco.languages.setMonarchTokensProvider('fortran', {
            defaultToken: 'identifier',
            ignoreCase: true,
            keywords: [
                'program','end','endprogram','subroutine','endsubroutine','function','endfunction',
                'module','endmodule','use','only','implicit','none','contains','type','endtype',
                'interface','endinterface','procedure','abstract','class','extends','generic',
                'if','then','else','elseif','endif','do','enddo','while','cycle','exit','continue',
                'select','case','endselect','default','return','call','stop','pause','format','goto',
                'parameter','dimension','allocatable','pointer','target','intent','in','out','inout',
                'private','public','save','external','intrinsic','optional','recursive','pure','elemental',
                'allocate','deallocate','nullify','associated','present','result','entry',
                'common','block','data','equivalence','include','namelist','open','close','read','write','print',
                'rewind','backspace','inquire','endfile','flush','where','forall','elsewhere','endwhere',
                'integer','real','complex','character','logical','doubleprecision','double','precision','kind',
            ],
            operators: ['+','-','*','/','**','//','=','==','/=','<','<=','>','>=','.eq.','.ne.','.lt.','.le.','.gt.','.ge.','.and.','.or.','.not.','.eqv.','.neqv.'],
            tokenizer: {
                root: [
                    [/!.*$/, 'comment'],
                    [/^[Cc*](?=\s)|^[Cc*]$/, 'comment.line.fortran'],
                    [/\s*#\s*\w+/, 'keyword.directive'],
                    [/"([^"\\]|\\.)*"/, 'string'],
                    [/'([^'\\]|\\.)*'/, 'string'],
                    [/\b\d+\.\d*([eEdD][+-]?\d+)?(_\w+)?/, 'number.float'],
                    [/\b\.\d+([eEdD][+-]?\d+)?(_\w+)?/, 'number.float'],
                    [/\b\d+([eEdD][+-]?\d+)(_\w+)?/, 'number.float'],
                    [/\b\d+(_\w+)?/, 'number'],
                    [/\.(true|false)\./i, 'constant.language.boolean'],
                    [/\.(eq|ne|lt|le|gt|ge|and|or|not|eqv|neqv)\./i, 'operator'],
                    [/[a-zA-Z_]\w*/, {
                        cases: { '@keywords': 'keyword', '@default': 'identifier' }
                    }],
                    [/[=<>!+\-*/]+/, 'operator'],
                    [/[;,.]/, 'delimiter'],
                ],
            },
        });
        monaco.languages.setLanguageConfiguration('fortran', {
            comments: { lineComment: '!' },
            brackets: [['(',')'],['[',']']],
            autoClosingPairs: [
                { open: '(', close: ')' },
                { open: '[', close: ']' },
                { open: '"', close: '"' },
                { open: "'", close: "'" },
            ],
            surroundingPairs: [
                { open: '(', close: ')' },
                { open: '[', close: ']' },
                { open: '"', close: '"' },
                { open: "'", close: "'" },
            ],
        });
    })();

    // ═════════════════════════════════════════════════════════════════════════
    // C — keywords, snippets, stdlib functions
    // ═════════════════════════════════════════════════════════════════════════
    const C_STATEMENT_KEYWORDS = new Set([
        'if','else','for','while','do','switch','case','default','break','continue',
        'return','goto','struct','union','enum','typedef','static','extern','const',
        'volatile','register','auto','inline','restrict','signed','unsigned','short','long',
    ]);

    function cKeywords(range) {
        const kw = (label, snippet, doc) => ({
            label, kind: K.Keyword, range,
            insertText: snippet || label,
            insertTextRules: snippet ? SNIP : 0,
            documentation: doc ? { value: doc } : '',
            sortText: '1_' + label,
        });
        return [
            kw('if',       'if (${1:cond}) {\n\t${0}\n}',                                      'if statement'),
            kw('else',     'else {\n\t${0}\n}',                                                 'else branch'),
            kw('for',      'for (int ${1:i} = 0; $1 < ${2:n}; $1++) {\n\t${0}\n}',              'for loop'),
            kw('while',    'while (${1:cond}) {\n\t${0}\n}',                                    'while loop'),
            kw('do',       'do {\n\t${0}\n} while (${1:cond});',                                'do-while'),
            kw('switch',   'switch (${1:expr}) {\n\tcase ${2:value}:\n\t\t${0}\n\t\tbreak;\n\tdefault:\n\t\tbreak;\n}', 'switch'),
            kw('case',     'case ${1:value}:\n\t${0}\n\tbreak;',                                'case label'),
            kw('default'), kw('break',  'break;'), kw('continue','continue;'),
            kw('return',   'return ${0};',                                                     'return'),
            kw('struct',   'struct ${1:Name} {\n\t${0}\n};',                                    'struct definition'),
            kw('union',    'union ${1:Name} {\n\t${0}\n};',                                    'union definition'),
            kw('enum',     'enum ${1:Name} {\n\t${0}\n};',                                     'enum definition'),
            kw('typedef',  'typedef ${1:struct type} ${2:Alias};',                              'typedef'),
            kw('static'),  kw('extern'), kw('const'), kw('volatile'), kw('inline'), kw('register'), kw('restrict'),
            kw('signed'),  kw('unsigned'), kw('short'), kw('long'), kw('goto'),
            kw('sizeof',   'sizeof(${1:type})', 'sizeof operator'),
            // Snippets
            kw('main',     'int main(int argc, char *argv[]) {\n\t${0}\n\treturn 0;\n}',        'main function boilerplate'),
            kw('include',  '#include <${1:stdio.h}>',                                           'preprocessor include'),
            kw('define',   '#define ${1:NAME} ${2:value}',                                      'preprocessor define'),
            kw('ifdef',    '#ifdef ${1:MACRO}\n${0}\n#endif',                                   'preprocessor ifdef'),
        ];
    }

    const C_LIB = {
        // ── stdio.h ──
        printf:   { sig: 'int printf(const char *format, ...)',            doc: 'Write formatted output to stdout.\n```c\nprintf("%d\\n", x);\n```' },
        scanf:    { sig: 'int scanf(const char *format, ...)',             doc: 'Read formatted input from stdin.\n```c\nscanf("%d", &x);\n```' },
        fprintf:  { sig: 'int fprintf(FILE *stream, const char *fmt, ...)',doc: 'Write formatted output to a stream.' },
        fscanf:   { sig: 'int fscanf(FILE *stream, const char *fmt, ...)', doc: 'Read formatted input from stream.' },
        sprintf:  { sig: 'int sprintf(char *str, const char *fmt, ...)',   doc: 'Format to a string buffer.' },
        snprintf: { sig: 'int snprintf(char *str, size_t n, const char *fmt, ...)', doc: 'Bounded formatted write to buffer.' },
        sscanf:   { sig: 'int sscanf(const char *str, const char *fmt, ...)', doc: 'Parse a formatted string.' },
        puts:     { sig: 'int puts(const char *s)',                         doc: 'Write string followed by newline to stdout.' },
        fputs:    { sig: 'int fputs(const char *s, FILE *stream)',          doc: 'Write string to a stream (no newline).' },
        getchar:  { sig: 'int getchar(void)',                               doc: 'Read a character from stdin.' },
        putchar:  { sig: 'int putchar(int c)',                              doc: 'Write a character to stdout.' },
        fgets:    { sig: 'char *fgets(char *s, int size, FILE *stream)',    doc: 'Read line from stream, includes newline.' },
        fopen:    { sig: 'FILE *fopen(const char *path, const char *mode)', doc: 'Open a file. Modes: "r","w","a","r+","w+","a+", + "b" for binary.\nReturns NULL on failure.' },
        fclose:   { sig: 'int fclose(FILE *stream)',                        doc: 'Close an open file stream.' },
        fread:    { sig: 'size_t fread(void *ptr, size_t size, size_t n, FILE *stream)', doc: 'Binary read.' },
        fwrite:   { sig: 'size_t fwrite(const void *ptr, size_t size, size_t n, FILE *stream)', doc: 'Binary write.' },
        fflush:   { sig: 'int fflush(FILE *stream)',                        doc: 'Flush buffered output.' },
        feof:     { sig: 'int feof(FILE *stream)',                          doc: 'Test end-of-file indicator.' },
        ferror:   { sig: 'int ferror(FILE *stream)',                        doc: 'Test error indicator.' },
        perror:   { sig: 'void perror(const char *s)',                      doc: 'Print errno-based error message.' },
        // ── stdlib.h ──
        malloc:   { sig: 'void *malloc(size_t size)',                       doc: 'Allocate `size` bytes. Returns NULL on failure.\n```c\nint *a = malloc(n * sizeof(int));\n```' },
        calloc:   { sig: 'void *calloc(size_t nmemb, size_t size)',         doc: 'Allocate + zero-initialize.' },
        realloc:  { sig: 'void *realloc(void *ptr, size_t size)',           doc: 'Resize allocation. May return new address.' },
        free:     { sig: 'void free(void *ptr)',                            doc: 'Free memory allocated by malloc/calloc/realloc.' },
        exit:     { sig: 'void exit(int status)',                           doc: 'Exit the program with the given status.' },
        atexit:   { sig: 'int atexit(void (*func)(void))',                  doc: 'Register a function to call at exit.' },
        atoi:     { sig: 'int atoi(const char *str)',                       doc: 'Parse integer from string.' },
        atof:     { sig: 'double atof(const char *str)',                    doc: 'Parse double from string.' },
        strtol:   { sig: 'long strtol(const char *str, char **endptr, int base)', doc: 'Parse long with error detection.' },
        strtod:   { sig: 'double strtod(const char *str, char **endptr)',   doc: 'Parse double with error detection.' },
        rand:     { sig: 'int rand(void)',                                  doc: 'Pseudo-random integer in [0, RAND_MAX].' },
        srand:    { sig: 'void srand(unsigned int seed)',                   doc: 'Seed the PRNG.' },
        qsort:    { sig: 'void qsort(void *base, size_t nmemb, size_t size, int (*cmp)(const void *, const void *))', doc: 'Sort an array using a comparator.' },
        bsearch:  { sig: 'void *bsearch(const void *key, const void *base, size_t nmemb, size_t size, int (*cmp)(const void *, const void *))', doc: 'Binary search sorted array.' },
        system:   { sig: 'int system(const char *command)',                 doc: 'Run shell command.' },
        getenv:   { sig: 'char *getenv(const char *name)',                  doc: 'Get environment variable value.' },
        abs:      { sig: 'int abs(int n)',                                  doc: 'Integer absolute value.' },
        // ── string.h ──
        strlen:   { sig: 'size_t strlen(const char *s)',                    doc: 'Length of null-terminated string.' },
        strcpy:   { sig: 'char *strcpy(char *dest, const char *src)',       doc: 'Copy null-terminated string. UNSAFE — use strncpy.' },
        strncpy:  { sig: 'char *strncpy(char *dest, const char *src, size_t n)', doc: 'Bounded string copy.' },
        strcmp:   { sig: 'int strcmp(const char *s1, const char *s2)',      doc: 'Lexicographic compare. 0 = equal.' },
        strncmp:  { sig: 'int strncmp(const char *s1, const char *s2, size_t n)', doc: 'Bounded compare.' },
        strcat:   { sig: 'char *strcat(char *dest, const char *src)',       doc: 'Append. UNSAFE — use strncat.' },
        strncat:  { sig: 'char *strncat(char *dest, const char *src, size_t n)', doc: 'Bounded append.' },
        strchr:   { sig: 'char *strchr(const char *s, int c)',              doc: 'Find first occurrence of c.' },
        strrchr:  { sig: 'char *strrchr(const char *s, int c)',             doc: 'Find last occurrence of c.' },
        strstr:   { sig: 'char *strstr(const char *haystack, const char *needle)', doc: 'Find substring.' },
        strtok:   { sig: 'char *strtok(char *str, const char *delim)',      doc: 'Tokenize string (stateful, NOT thread-safe).' },
        memcpy:   { sig: 'void *memcpy(void *dest, const void *src, size_t n)', doc: 'Copy n bytes. Buffers must not overlap.' },
        memmove:  { sig: 'void *memmove(void *dest, const void *src, size_t n)', doc: 'Copy n bytes (overlap safe).' },
        memset:   { sig: 'void *memset(void *s, int c, size_t n)',          doc: 'Fill n bytes with byte value c.' },
        memcmp:   { sig: 'int memcmp(const void *s1, const void *s2, size_t n)', doc: 'Compare byte ranges.' },
        memchr:   { sig: 'void *memchr(const void *s, int c, size_t n)',    doc: 'Find byte in range.' },
        // ── math.h ──
        sin:      { sig: 'double sin(double x)',       doc: 'Sine (radians).' },
        cos:      { sig: 'double cos(double x)',       doc: 'Cosine (radians).' },
        tan:      { sig: 'double tan(double x)',       doc: 'Tangent (radians).' },
        asin:     { sig: 'double asin(double x)',      doc: 'Arc sine.' },
        acos:     { sig: 'double acos(double x)',      doc: 'Arc cosine.' },
        atan:     { sig: 'double atan(double x)',      doc: 'Arc tangent.' },
        atan2:    { sig: 'double atan2(double y, double x)', doc: 'Arc tangent of y/x with quadrant.' },
        sqrt:     { sig: 'double sqrt(double x)',      doc: 'Square root.' },
        pow:      { sig: 'double pow(double x, double y)', doc: 'x raised to y.' },
        exp:      { sig: 'double exp(double x)',       doc: 'e^x.' },
        log:      { sig: 'double log(double x)',       doc: 'Natural log.' },
        log10:    { sig: 'double log10(double x)',     doc: 'Base-10 log.' },
        log2:     { sig: 'double log2(double x)',      doc: 'Base-2 log.' },
        floor:    { sig: 'double floor(double x)',     doc: 'Largest integer ≤ x.' },
        ceil:     { sig: 'double ceil(double x)',      doc: 'Smallest integer ≥ x.' },
        fabs:     { sig: 'double fabs(double x)',      doc: 'Float absolute value.' },
        fmod:     { sig: 'double fmod(double x, double y)', doc: 'Float remainder.' },
        round:    { sig: 'double round(double x)',     doc: 'Round to nearest.' },
        // ── ctype.h ──
        isalpha:  { sig: 'int isalpha(int c)',      doc: 'Is alphabetic?' },
        isdigit:  { sig: 'int isdigit(int c)',      doc: 'Is digit?' },
        isalnum:  { sig: 'int isalnum(int c)',      doc: 'Is alphanumeric?' },
        isspace:  { sig: 'int isspace(int c)',      doc: 'Is whitespace?' },
        isupper:  { sig: 'int isupper(int c)',      doc: 'Is uppercase?' },
        islower:  { sig: 'int islower(int c)',      doc: 'Is lowercase?' },
        toupper:  { sig: 'int toupper(int c)',      doc: 'To uppercase.' },
        tolower:  { sig: 'int tolower(int c)',      doc: 'To lowercase.' },
        // ── time.h ──
        time:     { sig: 'time_t time(time_t *tloc)',    doc: 'Seconds since epoch. Pass NULL or address.' },
        clock:    { sig: 'clock_t clock(void)',          doc: 'CPU time since program start.' },
        difftime: { sig: 'double difftime(time_t end, time_t beg)', doc: 'Seconds between two times.' },
        strftime: { sig: 'size_t strftime(char *s, size_t max, const char *fmt, const struct tm *tm)', doc: 'Format a time value.' },
        localtime:{ sig: 'struct tm *localtime(const time_t *t)', doc: 'Convert to local time. Returns pointer to static buffer.' },
        // ── assert.h ──
        assert:   { sig: 'void assert(int expression)', doc: 'Abort if expression is false (unless NDEBUG).' },
        // Constants
        NULL:     { sig: 'NULL', doc: 'Null pointer.', kind: 'const' },
        EOF:      { sig: 'EOF',  doc: 'End-of-file indicator (−1).', kind: 'const' },
        stdin:    { sig: 'stdin',  doc: 'Standard input stream.',  kind: 'var' },
        stdout:   { sig: 'stdout', doc: 'Standard output stream.', kind: 'var' },
        stderr:   { sig: 'stderr', doc: 'Standard error stream.',  kind: 'var' },
        EXIT_SUCCESS: { sig: 'EXIT_SUCCESS', doc: '0 — normal exit status.', kind: 'const' },
        EXIT_FAILURE: { sig: 'EXIT_FAILURE', doc: '1 — error exit status.', kind: 'const' },
        RAND_MAX: { sig: 'RAND_MAX', doc: 'Maximum value returned by rand().', kind: 'const' },
        // Types
        size_t:   { sig: 'size_t',  doc: 'Unsigned type for sizes.', kind: 'class' },
        FILE:     { sig: 'FILE',    doc: 'File stream object.',     kind: 'class' },
        time_t:   { sig: 'time_t',  doc: 'Time value.',             kind: 'class' },
        clock_t:  { sig: 'clock_t', doc: 'CPU clock ticks.',        kind: 'class' },
    };

    // ═════════════════════════════════════════════════════════════════════════
    // C++ — extends C with std:: library
    // ═════════════════════════════════════════════════════════════════════════
    const CPP_STATEMENT_KEYWORDS = new Set([
        ...C_STATEMENT_KEYWORDS,
        'class','public','private','protected','virtual','override','final','explicit','friend',
        'template','typename','namespace','using','try','catch','throw','new','delete','this',
        'operator','constexpr','consteval','constinit','noexcept','decltype','auto','nullptr',
        'mutable','typeid','co_await','co_yield','co_return',
        // Snippets
        'main','include','define','forauto','ifmain',
    ]);

    function cppKeywords(range) {
        const kw = (label, snippet, doc) => ({
            label, kind: K.Keyword, range,
            insertText: snippet || label,
            insertTextRules: snippet ? SNIP : 0,
            documentation: doc ? { value: doc } : '',
            sortText: '1_' + label,
        });
        return [
            ...cKeywords(range),
            // C++ specific
            kw('class',    'class ${1:Name} {\npublic:\n\t${1:Name}();\n\t~${1:Name}();\n\n\t${0}\nprivate:\n};', 'class definition'),
            kw('namespace','namespace ${1:ns} {\n\t${0}\n}',                                    'namespace'),
            kw('template', 'template <typename ${1:T}>\n',                                       'template declaration'),
            kw('try',      'try {\n\t${1}\n} catch (const ${2:std::exception}& ${3:e}) {\n\t${0}\n}', 'try/catch'),
            kw('catch',    'catch (const ${1:std::exception}& ${2:e}) {\n\t${0}\n}',            'catch'),
            kw('using',    'using ${1:alias} = ${2:type};',                                     'type alias'),
            kw('usingns',  'using namespace ${1:std};',                                         'using namespace'),
            kw('new',      'new ${1:Type}(${2:args})',                                          'new operator'),
            kw('delete',   'delete ${0};',                                                     'delete operator'),
            kw('throw',    'throw ${0};',                                                      'throw exception'),
            kw('public'),  kw('private'), kw('protected'), kw('virtual'), kw('override'),
            kw('final'),   kw('explicit'), kw('friend'), kw('mutable'), kw('constexpr'),
            kw('consteval'), kw('nullptr'), kw('noexcept'), kw('decltype'),
            kw('auto'),    kw('operator'), kw('this'), kw('typename'),
            kw('static_cast',      'static_cast<${1:T}>(${2:expr})',      'Compile-time safe cast.'),
            kw('dynamic_cast',     'dynamic_cast<${1:T}>(${2:expr})',     'Runtime-checked downcast.'),
            kw('const_cast',       'const_cast<${1:T}>(${2:expr})',       'Strip/add const.'),
            kw('reinterpret_cast', 'reinterpret_cast<${1:T}>(${2:expr})', 'Unsafe pointer cast.'),
            // Useful C++ snippets
            kw('forauto',  'for (auto& ${1:item} : ${2:collection}) {\n\t${0}\n}',              'Range-based for'),
            kw('forit',    'for (auto it = ${1:container}.begin(); it != $1.end(); ++it) {\n\t${0}\n}', 'Iterator loop'),
            kw('mainCPP',  '#include <iostream>\n\nint main(int argc, char* argv[]) {\n\t${0:std::cout << "Hello, World!\\n";}\n\treturn 0;\n}', 'C++ main boilerplate'),
            kw('lambda',   '[${1:&}](${2:args}) {\n\t${0}\n}',                                  'lambda expression'),
        ];
    }

    const CPP_LIB = {
        ...C_LIB,
        // ── std:: streams ──
        cout:     { sig: 'std::cout',  doc: 'Standard output stream. Use `<<` to write.\n```cpp\nstd::cout << "x = " << x << std::endl;\n```', kind: 'var' },
        cerr:     { sig: 'std::cerr',  doc: 'Standard error stream.', kind: 'var' },
        cin:      { sig: 'std::cin',   doc: 'Standard input stream. Use `>>` to read.', kind: 'var' },
        endl:     { sig: 'std::endl',  doc: 'End-of-line + flush.', kind: 'var' },
        // ── <string> ──
        string:   { sig: 'std::string', doc: 'Dynamically-sized string.', kind: 'class' },
        to_string:{ sig: 'std::string to_string(T value)', doc: 'Convert numeric to string.' },
        stoi:     { sig: 'int std::stoi(const std::string& s, size_t* pos = 0, int base = 10)', doc: 'Parse integer.' },
        stod:     { sig: 'double std::stod(const std::string& s)', doc: 'Parse double.' },
        stoll:    { sig: 'long long std::stoll(const std::string& s)', doc: 'Parse long long.' },
        // ── <vector> ──
        vector:   { sig: 'std::vector<T>', doc: 'Dynamic array.\n```cpp\nstd::vector<int> v = {1, 2, 3};\nv.push_back(4);\n```', kind: 'class' },
        // ── <array> <list> <deque> <map> <set> <unordered_*> ──
        array:    { sig: 'std::array<T, N>', doc: 'Fixed-size array.', kind: 'class' },
        list:     { sig: 'std::list<T>', doc: 'Doubly-linked list.', kind: 'class' },
        deque:    { sig: 'std::deque<T>', doc: 'Double-ended queue.', kind: 'class' },
        map:      { sig: 'std::map<K, V>', doc: 'Red-black tree map (ordered).', kind: 'class' },
        unordered_map: { sig: 'std::unordered_map<K, V>', doc: 'Hash map.', kind: 'class' },
        set:      { sig: 'std::set<T>', doc: 'Red-black tree set (ordered).', kind: 'class' },
        unordered_set: { sig: 'std::unordered_set<T>', doc: 'Hash set.', kind: 'class' },
        pair:     { sig: 'std::pair<A, B>', doc: 'Two-element tuple.', kind: 'class' },
        tuple:    { sig: 'std::tuple<T...>', doc: 'Fixed-size heterogeneous collection.', kind: 'class' },
        make_pair:{ sig: 'std::pair<A,B> make_pair(A a, B b)', doc: 'Construct a pair.' },
        make_tuple:{ sig: 'std::tuple<T...> make_tuple(Args&&... args)', doc: 'Construct a tuple.' },
        // ── <memory> ──
        unique_ptr:{ sig: 'std::unique_ptr<T>', doc: 'Owning single-owner smart pointer.', kind: 'class' },
        shared_ptr:{ sig: 'std::shared_ptr<T>', doc: 'Reference-counted smart pointer.', kind: 'class' },
        weak_ptr: { sig: 'std::weak_ptr<T>', doc: 'Non-owning observer for shared_ptr.', kind: 'class' },
        make_unique:{ sig: 'std::unique_ptr<T> make_unique<T>(Args&&... args)', doc: 'Construct a unique_ptr.\n```cpp\nauto p = std::make_unique<MyClass>(arg1, arg2);\n```' },
        make_shared:{ sig: 'std::shared_ptr<T> make_shared<T>(Args&&... args)', doc: 'Construct a shared_ptr.' },
        // ── <algorithm> ──
        sort:     { sig: 'void std::sort(It first, It last)', doc: 'Sort in-place.' },
        stable_sort: { sig: 'void std::stable_sort(It first, It last)', doc: 'Sort preserving order of equal elements.' },
        find:     { sig: 'It std::find(It first, It last, const T& value)', doc: 'Linear search.' },
        find_if:  { sig: 'It std::find_if(It first, It last, UnaryPredicate p)', doc: 'Find first matching element.' },
        count:    { sig: 'iterator_traits<It>::difference_type std::count(It first, It last, const T& value)', doc: 'Count equal elements.' },
        count_if: { sig: 'auto std::count_if(It first, It last, Predicate p)', doc: 'Count matching elements.' },
        copy:     { sig: 'OutIt std::copy(It first, It last, OutIt dst)', doc: 'Copy range.' },
        transform:{ sig: 'OutIt std::transform(It first, It last, OutIt dst, UnaryOp op)', doc: 'Apply op to each element.' },
        accumulate:{ sig: 'T std::accumulate(It first, It last, T init)', doc: 'Sum / fold elements.' },
        reverse:  { sig: 'void std::reverse(It first, It last)', doc: 'Reverse in-place.' },
        min:      { sig: 'const T& std::min(const T& a, const T& b)', doc: 'Minimum.' },
        max:      { sig: 'const T& std::max(const T& a, const T& b)', doc: 'Maximum.' },
        min_element: { sig: 'It std::min_element(It first, It last)', doc: 'Iterator to smallest.' },
        max_element: { sig: 'It std::max_element(It first, It last)', doc: 'Iterator to largest.' },
        swap:     { sig: 'void std::swap(T& a, T& b)', doc: 'Swap two values.' },
        move:     { sig: 'T&& std::move(T& x)', doc: 'Cast to rvalue reference.' },
        forward:  { sig: 'T&& std::forward<T>(U&& u)', doc: 'Perfect-forward argument.' },
        // ── <iostream> / <fstream> ──
        ifstream: { sig: 'std::ifstream', doc: 'Input file stream.', kind: 'class' },
        ofstream: { sig: 'std::ofstream', doc: 'Output file stream.', kind: 'class' },
        fstream:  { sig: 'std::fstream',  doc: 'Bidirectional file stream.', kind: 'class' },
        // ── <thread> <chrono> ──
        thread:   { sig: 'std::thread', doc: 'OS thread.', kind: 'class' },
        async:    { sig: 'std::future<R> std::async(std::launch policy, F&& f, Args&&... args)', doc: 'Launch async task.' },
        mutex:    { sig: 'std::mutex', doc: 'Mutual-exclusion primitive.', kind: 'class' },
        lock_guard:{ sig: 'std::lock_guard<M>', doc: 'RAII mutex guard.', kind: 'class' },
        // ── <exception> ──
        exception:     { sig: 'std::exception',     doc: 'Base exception class.', kind: 'class' },
        runtime_error: { sig: 'std::runtime_error', doc: 'Runtime error exception.', kind: 'class' },
        logic_error:   { sig: 'std::logic_error',   doc: 'Logic error exception.', kind: 'class' },
        invalid_argument: { sig: 'std::invalid_argument', doc: 'Invalid argument exception.', kind: 'class' },
        out_of_range:  { sig: 'std::out_of_range',  doc: 'Out-of-range exception.', kind: 'class' },
    };

    // Include headers
    const CPP_INCLUDES = [
        ['<iostream>',      'std::cout, std::cin, std::cerr'],
        ['<string>',        'std::string, std::to_string'],
        ['<vector>',        'std::vector'],
        ['<array>',         'std::array'],
        ['<map>',           'std::map'],
        ['<unordered_map>', 'std::unordered_map'],
        ['<set>',           'std::set'],
        ['<unordered_set>', 'std::unordered_set'],
        ['<algorithm>',     'std::sort, std::find, std::copy, …'],
        ['<memory>',        'std::unique_ptr, std::shared_ptr'],
        ['<fstream>',       'std::ifstream, std::ofstream'],
        ['<sstream>',       'std::stringstream'],
        ['<chrono>',        'std::chrono::*'],
        ['<thread>',        'std::thread'],
        ['<mutex>',         'std::mutex, std::lock_guard'],
        ['<cmath>',         'sin, cos, sqrt, pow, …'],
        ['<cstring>',       'memcpy, strlen, …'],
        ['<cstdlib>',       'malloc, free, exit, …'],
        ['<cstdio>',        'printf, scanf, fopen, …'],
        ['<stdexcept>',     'std::runtime_error, …'],
        ['<utility>',       'std::pair, std::move, std::swap'],
        ['<tuple>',         'std::tuple, std::make_tuple'],
        ['<numeric>',       'std::accumulate, std::iota'],
        ['<functional>',    'std::function, std::bind'],
    ];
    const C_INCLUDES = [
        ['<stdio.h>',   'printf, scanf, fopen, fclose, …'],
        ['<stdlib.h>',  'malloc, free, exit, atoi, rand, …'],
        ['<string.h>',  'strlen, strcpy, strcmp, memcpy, …'],
        ['<math.h>',    'sin, cos, sqrt, pow, log, …'],
        ['<time.h>',    'time, clock, strftime, …'],
        ['<ctype.h>',   'isalpha, isdigit, toupper, …'],
        ['<assert.h>',  'assert'],
        ['<stddef.h>',  'size_t, ptrdiff_t, NULL'],
        ['<stdint.h>',  'int8_t, int32_t, uint64_t, …'],
        ['<limits.h>',  'INT_MAX, INT_MIN, CHAR_BIT, …'],
        ['<float.h>',   'DBL_MAX, FLT_EPSILON, …'],
        ['<errno.h>',   'errno, strerror'],
    ];

    // ═════════════════════════════════════════════════════════════════════════
    // FORTRAN — keywords + intrinsics
    // ═════════════════════════════════════════════════════════════════════════
    const FORTRAN_STATEMENT_KEYWORDS = new Set([
        'program','subroutine','function','module','use','implicit','contains','type',
        'interface','procedure','if','then','else','elseif','endif','do','enddo','while',
        'cycle','exit','select','case','default','return','call','stop','continue','format',
        'parameter','dimension','allocatable','pointer','target','intent','private','public',
        'integer','real','complex','character','logical','end',
    ]);

    function fortranKeywords(range) {
        const kw = (label, snippet, doc) => ({
            label, kind: K.Keyword, range,
            insertText: snippet || label,
            insertTextRules: snippet ? SNIP : 0,
            documentation: doc ? { value: doc } : '',
            sortText: '1_' + label,
        });
        return [
            kw('program',   'program ${1:name}\n\timplicit none\n\t${0}\nend program $1',        'Main program unit'),
            kw('subroutine','subroutine ${1:name}(${2:args})\n\timplicit none\n\t${0}\nend subroutine $1', 'Subroutine'),
            kw('function',  'function ${1:name}(${2:args}) result(${3:res})\n\timplicit none\n\t${0}\nend function $1', 'Function'),
            kw('module',    'module ${1:name}\n\timplicit none\n\t${0}\ncontains\nend module $1', 'Module'),
            kw('use',       'use ${1:module}',                                                   'Import a module'),
            kw('implicit',  'implicit none',                                                     'Disable implicit typing'),
            kw('if',        'if (${1:cond}) then\n\t${0}\nend if',                               'if-then-end if'),
            kw('elseif',    'else if (${1:cond}) then\n\t${0}',                                  'else-if branch'),
            kw('else',      'else\n\t${0}',                                                     'else branch'),
            kw('do',        'do ${1:i} = ${2:1}, ${3:n}\n\t${0}\nend do',                        'Counted do-loop'),
            kw('dowhile',   'do while (${1:cond})\n\t${0}\nend do',                              'Conditional do-loop'),
            kw('select',    'select case (${1:expr})\ncase (${2:value})\n\t${0}\ncase default\nend select', 'select-case'),
            kw('type',      'type :: ${1:TypeName}\n\t${0}\nend type $1',                        'Derived type'),
            kw('interface', 'interface\n\t${0}\nend interface',                                  'Interface block'),
            kw('integer'),  kw('real'), kw('complex'), kw('logical'),
            kw('character', 'character(len=${1:256})',   'character with length'),
            kw('doubleprecision', 'double precision'),
            kw('parameter', 'parameter (${1:name} = ${2:value})',                               'Named constant'),
            kw('dimension', 'dimension(${1:n})',                                                 'Array declaration'),
            kw('allocatable'), kw('pointer'), kw('target'),
            kw('intent',    'intent(${1|in,out,inout|})',                                        'Dummy arg intent'),
            kw('allocate',  'allocate(${1:array}(${2:size}))',                                   'Allocate array'),
            kw('deallocate','deallocate(${1:array})',                                            'Deallocate array'),
            kw('private'),  kw('public'), kw('contains'), kw('return'), kw('cycle'), kw('exit'),
            kw('stop',      'stop ${1:"message"}'), kw('continue'),
            kw('call',      'call ${1:subroutine}(${2:args})',                                   'Call subroutine'),
            // Module-level snippets
            kw('main',      'program ${1:main}\n\timplicit none\n\t${0}\nend program $1',       'Fortran main boilerplate'),
        ];
    }

    const FORTRAN_LIB = {
        // I/O
        print:    { sig: 'print *, <list>',              doc: 'Unformatted print to stdout.\n```fortran\nprint *, "x =", x\n```' },
        write:    { sig: 'write(unit, fmt) <list>',       doc: 'Formatted write.\n```fortran\nwrite(*, "(F10.3)") x\n```' },
        read:     { sig: 'read(unit, fmt) <list>',        doc: 'Formatted read.' },
        open:     { sig: 'open(unit=N, file="path", status=...)', doc: 'Open file unit. Status: "old"/"new"/"replace"/"unknown".' },
        close:    { sig: 'close(unit=N)',                 doc: 'Close file unit.' },
        rewind:   { sig: 'rewind(unit=N)',                doc: 'Rewind file.' },
        backspace:{ sig: 'backspace(unit=N)',             doc: 'Back up one record.' },
        // Array intrinsics
        size:     { sig: 'integer size(array, dim)',      doc: 'Array extent.' },
        shape:    { sig: 'integer shape(array)',          doc: 'Array shape vector.' },
        reshape:  { sig: 'reshape(source, shape)',         doc: 'Reshape array.' },
        sum:      { sig: 'sum(array, dim, mask)',         doc: 'Sum of elements.' },
        product:  { sig: 'product(array, dim, mask)',     doc: 'Product of elements.' },
        maxval:   { sig: 'maxval(array, dim, mask)',      doc: 'Maximum value.' },
        minval:   { sig: 'minval(array, dim, mask)',      doc: 'Minimum value.' },
        maxloc:   { sig: 'integer maxloc(array, dim, mask)', doc: 'Index of maximum.' },
        minloc:   { sig: 'integer minloc(array, dim, mask)', doc: 'Index of minimum.' },
        count:    { sig: 'integer count(mask, dim)',      doc: 'Count true values.' },
        any:      { sig: 'logical any(mask, dim)',        doc: 'True if any element true.' },
        all:      { sig: 'logical all(mask, dim)',        doc: 'True if all elements true.' },
        // Math
        abs:      { sig: 'abs(x)',      doc: 'Absolute value.' },
        sqrt:     { sig: 'sqrt(x)',     doc: 'Square root.' },
        exp:      { sig: 'exp(x)',      doc: 'e^x.' },
        log:      { sig: 'log(x)',      doc: 'Natural log.' },
        log10:    { sig: 'log10(x)',    doc: 'Base-10 log.' },
        sin:      { sig: 'sin(x)',      doc: 'Sine (radians).' },
        cos:      { sig: 'cos(x)',      doc: 'Cosine (radians).' },
        tan:      { sig: 'tan(x)',      doc: 'Tangent (radians).' },
        asin:     { sig: 'asin(x)',     doc: 'Arc sine.' },
        acos:     { sig: 'acos(x)',     doc: 'Arc cosine.' },
        atan:     { sig: 'atan(x)',     doc: 'Arc tangent.' },
        atan2:    { sig: 'atan2(y, x)', doc: 'Arc tangent of y/x.' },
        floor:    { sig: 'floor(x)',    doc: 'Floor.' },
        ceiling:  { sig: 'ceiling(x)',  doc: 'Ceiling.' },
        mod:      { sig: 'mod(a, p)',   doc: 'Remainder.' },
        modulo:   { sig: 'modulo(a, p)',doc: 'Modulo (same sign as divisor).' },
        nint:     { sig: 'nint(x)',     doc: 'Nearest integer.' },
        // Type conversion
        real:     { sig: 'real(x, kind)',     doc: 'Convert to real.' },
        int:      { sig: 'int(x, kind)',      doc: 'Convert to integer.' },
        dble:     { sig: 'dble(x)',           doc: 'Convert to double precision.' },
        cmplx:    { sig: 'cmplx(x, y, kind)', doc: 'Construct complex.' },
        // Character
        len:      { sig: 'integer len(string)',         doc: 'String length.' },
        trim:     { sig: 'character trim(string)',      doc: 'Trim trailing spaces.' },
        index:    { sig: 'integer index(string, substr, back)', doc: 'Find substring position.' },
        achar:    { sig: 'character achar(i)',           doc: 'ASCII code → character.' },
        iachar:   { sig: 'integer iachar(c)',            doc: 'Character → ASCII code.' },
        // Allocate / memory
        allocated:{ sig: 'logical allocated(array)',     doc: 'Is array allocated?' },
        associated:{ sig: 'logical associated(pointer, target)', doc: 'Is pointer associated?' },
        present:  { sig: 'logical present(arg)',         doc: 'Is optional argument present?' },
        // Constants
        '.true.': { sig: '.true.',  doc: 'Logical true.', kind: 'const' },
        '.false.':{ sig: '.false.', doc: 'Logical false.', kind: 'const' },
    };

    // ═════════════════════════════════════════════════════════════════════════
    // HELPERS — shared between the 3 languages
    // ═════════════════════════════════════════════════════════════════════════
    function libCompletions(lib, range) {
        const out = [];
        for (const name in lib) {
            const spec = lib[name];
            const kind = spec.kind === 'class' ? K.Class
                       : spec.kind === 'const' ? K.Constant
                       : spec.kind === 'var'   ? K.Variable
                       : K.Function;
            const isCallable = kind === K.Function;
            out.push({
                label: name,
                kind: kind,
                range,
                insertText: isCallable ? name + '(${0})' : name,
                insertTextRules: SNIP,
                detail: spec.sig,
                documentation: spec.doc ? { value: spec.doc } : '',
                sortText: '3_' + name,
            });
        }
        return out;
    }

    function libSignatureDB(lib) {
        const sigs = {};
        for (const name in lib) {
            const spec = lib[name];
            if (!spec.sig) continue;
            const m = spec.sig.match(/^(?:[\w:\s\*&<>]+\s+)?(\w+)\(([\s\S]*?)\)(.*)$/);
            if (!m) continue;
            const params = m[2].split(/,(?![^<(]*[>)])/)
                .map(s => s.trim()).filter(Boolean)
                .map(s => p(s, '**' + s + '**'));
            sigs[name] = [{ label: spec.sig, doc: spec.doc || '', params }];
        }
        return sigs;
    }

    function getCallInfo(model, position) {
        const lineContent = model.getLineContent(position.lineNumber);
        const col = position.column - 1;
        let depth = 0, i = col - 1, activeParam = 0;
        while (i >= 0) {
            const ch = lineContent[i];
            if (ch === ')' || ch === ']' || ch === '}') depth++;
            else if (ch === '(' || ch === '[' || ch === '{') {
                if (depth === 0 && ch === '(') {
                    let j = i - 1;
                    while (j >= 0 && /[\w:]/.test(lineContent[j])) j--;
                    const fnName = lineContent.slice(j + 1, i).split(/[.:]/).pop();
                    return { fnName, activeParam };
                }
                depth--;
            } else if (ch === ',' && depth === 0) activeParam++;
            i--;
        }
        return null;
    }

    // ═════════════════════════════════════════════════════════════════════════
    // C PROVIDER
    // ═════════════════════════════════════════════════════════════════════════
    const C_SIG_DB = libSignatureDB(C_LIB);
    function registerLanguage(langId, keywordsFn, lib, sigDb, stmtKeywords, includes) {
        monaco.languages.registerCompletionItemProvider(langId, {
            triggerCharacters: ['.', ' ', '(', ',', '<', '>', ':', '#', '_'],
            provideCompletionItems(model, position) {
                const range = mkRange(model, position);
                const prefix = linePrefix(model, position);
                const atLineStart = isAtLineStart(model, position);

                // `#include <` → suggest header names
                if (/^\s*#\s*include\s*<?\w*$/.test(prefix)) {
                    return { suggestions: includes.map(([hdr, doc]) => ({
                        label: hdr, kind: K.File, range,
                        insertText: hdr,
                        detail: doc, sortText: '0_' + hdr,
                    })) };
                }

                // `std::` prefix (C++ only)
                if (langId === 'cpp' && /\bstd::\w*$/.test(prefix)) {
                    return { suggestions: libCompletions(lib, range)
                        .filter(x => x.detail && x.detail.startsWith('std::')) };
                }

                // Filter statement keywords when NOT at line start
                const kwList = keywordsFn(range).filter(k => {
                    if (stmtKeywords.has(k.label) && !atLineStart) return false;
                    return true;
                });

                return { suggestions: [
                    ...kwList,
                    ...libCompletions(lib, range),
                ]};
            },
        });

        monaco.languages.registerSignatureHelpProvider(langId, {
            signatureHelpTriggerCharacters:   ['(', ','],
            signatureHelpRetriggerCharacters: [','],
            provideSignatureHelp(model, position) {
                const info = getCallInfo(model, position);
                if (!info || !info.fnName) return null;
                const sigs = sigDb[info.fnName];
                if (!sigs || sigs.length === 0) return null;
                const sig = sigs[0];
                return {
                    value: {
                        activeSignature: 0,
                        activeParameter: Math.min(info.activeParam, sig.params.length - 1),
                        signatures: [{
                            label: sig.label,
                            documentation: { value: sig.doc || '' },
                            parameters: sig.params.map(pp => ({
                                label: pp.label,
                                documentation: pp.doc ? { value: pp.doc } : undefined,
                            })),
                        }],
                    },
                    dispose() {},
                };
            },
        });

        monaco.languages.registerHoverProvider(langId, {
            provideHover(model, position) {
                const word = model.getWordAtPosition(position);
                if (!word) return null;
                const spec = lib[word.word];
                if (!spec) return null;
                const lines = [];
                if (spec.sig) lines.push('```' + langId + '\n' + spec.sig + '\n```');
                if (spec.doc) lines.push(spec.doc);
                return {
                    range: new monaco.Range(position.lineNumber, word.startColumn, position.lineNumber, word.endColumn),
                    contents: [{ value: lines.join('\n\n') }],
                };
            },
        });
    }

    registerLanguage('c',       cKeywords,       C_LIB,       C_SIG_DB,       C_STATEMENT_KEYWORDS,       C_INCLUDES);
    registerLanguage('cpp',     cppKeywords,     CPP_LIB,     libSignatureDB(CPP_LIB), CPP_STATEMENT_KEYWORDS, CPP_INCLUDES);
    registerLanguage('fortran', fortranKeywords, FORTRAN_LIB, libSignatureDB(FORTRAN_LIB), FORTRAN_STATEMENT_KEYWORDS, []);

    console.log('[editor-langs.js] C / C++ / Fortran providers registered (' +
        Object.keys(C_LIB).length + ' C, ' + Object.keys(CPP_LIB).length + ' C++, ' +
        Object.keys(FORTRAN_LIB).length + ' Fortran symbols)');
};

// ═══════════════════════════════════════════════════════════════════════════
// BUNDLED ENTRY POINT — the single function editor.html calls after Monaco
// mounts. Registers IntelliSense for every supported language (Python, C,
// C++, Fortran) in one shot.
//
// Design note: we don't use a real Language Server (VS Code's cpptools needs
// a C/C++ compiler + caching directory; fortls is Python-based). Those
// assumptions don't hold on iPadOS. Instead, every language ships a static
// symbol DB + Monarch tokenizer + custom providers — fast, no network, and
// no dependencies. ~400 Python symbols, 60+ C stdlib, 100+ C++ std::, 50+
// Fortran intrinsics.
// ═══════════════════════════════════════════════════════════════════════════
window.registerAllLanguageProviders = function (monaco, editor) {
    if (typeof window.registerPythonProviders === 'function') {
        window.registerPythonProviders(monaco, editor);
    }
    if (typeof window.registerCLanguages === 'function') {
        window.registerCLanguages(monaco, editor);
    }
    console.log('[editor.js] All language providers bundled — Python / C / C++ / Fortran');
};
