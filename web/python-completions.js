/**
 * Manim Studio - Python & Manim Completion Provider
 *
 * Registers context-aware IntelliSense for Monaco Editor:
 *   - Python 3 keywords & builtins with snippets
 *   - All Manim scene types, animations, mobjects, colors, constants
 *   - Context detection: after 'self.' shows only scene methods
 *   - Context detection: after 'from manim import' shows only Manim symbols
 *   - Hover docs for frequently-used Manim items
 *
 * Zero backend dependency — runs entirely client-side, instant startup.
 * Call window.registerManimCompletions(monaco) after Monaco is loaded.
 */
window.registerManimCompletions = function (monaco) {
    const K    = monaco.languages.CompletionItemKind;
    const SNIP = monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet;

    // ── helpers ──────────────────────────────────────────────────────────────
    function mkRange(model, position) {
        const w = model.getWordUntilPosition(position);
        return {
            startLineNumber: position.lineNumber,
            endLineNumber:   position.lineNumber,
            startColumn:     w.startColumn,
            endColumn:       w.endColumn,
        };
    }

    // text on the current line, from col-1 to just before the current word
    function linePrefix(model, position) {
        const w = model.getWordUntilPosition(position);
        return model.getValueInRange({
            startLineNumber: position.lineNumber,
            startColumn: 1,
            endLineNumber: position.lineNumber,
            endColumn: w.startColumn,
        });
    }

    // ── Python keywords ───────────────────────────────────────────────────────
    function kwItems(range) {
        const kw = (label, snippet, doc) => ({
            label, kind: K.Keyword, range,
            insertText: snippet || label,
            insertTextRules: snippet ? SNIP : 0,
            documentation: doc || '',
        });
        return [
            kw('def',      'def ${1:name}(${2:args}):\n\t${0:pass}',                        'Define a function'),
            kw('class',    'class ${1:Name}(${2:object}):\n\t${0:pass}',                    'Define a class'),
            kw('import',   'import ${1:module}',                                             'Import a module'),
            kw('from',     'from ${1:module} import ${2:name}',                             'Import from a module'),
            kw('if',       'if ${1:condition}:\n\t${0:pass}',                               'If statement'),
            kw('elif',     'elif ${1:condition}:\n\t${0:pass}',                             'Elif clause'),
            kw('else',     'else:\n\t${0:pass}',                                            'Else clause'),
            kw('for',      'for ${1:item} in ${2:iterable}:\n\t${0:pass}',                 'For loop'),
            kw('while',    'while ${1:condition}:\n\t${0:pass}',                            'While loop'),
            kw('try',      'try:\n\t${1:pass}\nexcept ${2:Exception} as ${3:e}:\n\t${0:pass}', 'Try/except block'),
            kw('except'),
            kw('finally',  'finally:\n\t${0:pass}'),
            kw('with',     'with ${1:expr} as ${2:name}:\n\t${0:pass}'),
            kw('as'),
            kw('return',   'return ${0}'),
            kw('yield',    'yield ${0}'),
            kw('lambda',   'lambda ${1:args}: ${0:expr}'),
            kw('async',    'async def ${1:name}(${2:args}):\n\t${0:pass}'),
            kw('await',    'await ${0}'),
            kw('pass'),
            kw('break'),
            kw('continue'),
            kw('raise',    'raise ${1:Exception}(${0})'),
            kw('del',      'del ${0}'),
            kw('global',   'global ${0}'),
            kw('nonlocal', 'nonlocal ${0}'),
            kw('not'),
            kw('and'),
            kw('or'),
            kw('in'),
            kw('is'),
            kw('True'),
            kw('False'),
            kw('None'),
            kw('assert',   'assert ${1:condition}, ${2:"message"}'),
        ];
    }

    // ── Python builtins ───────────────────────────────────────────────────────
    function builtinItems(range) {
        const fn = (label, snippet, doc) => ({
            label, kind: K.Function, range,
            insertText: snippet || (label + '(${0})'),
            insertTextRules: SNIP,
            documentation: doc || '',
        });
        return [
            fn('print',      'print(${0})',                              'Print to stdout'),
            fn('len',        'len(${1:obj})',                            'Return the length of an object'),
            fn('range',      'range(${1:stop})',                         'Return a range object'),
            fn('list',       'list(${0})',                               'Create a list'),
            fn('dict',       'dict(${0})',                               'Create a dictionary'),
            fn('set',        'set(${0})',                                'Create a set'),
            fn('tuple',      'tuple(${0})',                              'Create a tuple'),
            fn('str',        'str(${1:obj})',                            'Convert to string'),
            fn('int',        'int(${1:obj})',                            'Convert to integer'),
            fn('float',      'float(${1:obj})',                          'Convert to float'),
            fn('bool',       'bool(${1:obj})',                           'Convert to boolean'),
            fn('type',       'type(${1:obj})',                           'Get the type of an object'),
            fn('isinstance', 'isinstance(${1:obj}, ${2:type})',          'Check if obj is instance of type'),
            fn('hasattr',    'hasattr(${1:obj}, ${2:"attr"})',           'Check if attribute exists'),
            fn('getattr',    'getattr(${1:obj}, ${2:"attr"})',           'Get an attribute value'),
            fn('setattr',    'setattr(${1:obj}, ${2:"attr"}, ${3:val})', 'Set an attribute value'),
            fn('enumerate',  'enumerate(${1:iterable})',                 'Enumerate with (index, value) pairs'),
            fn('zip',        'zip(${1:iter1}, ${2:iter2})',              'Zip multiple iterables'),
            fn('map',        'map(${1:func}, ${2:iterable})',            'Apply function to each element'),
            fn('filter',     'filter(${1:func}, ${2:iterable})',         'Filter elements by function'),
            fn('sorted',     'sorted(${1:iterable})',                    'Return sorted list'),
            fn('reversed',   'reversed(${1:iterable})',                  'Return reversed iterator'),
            fn('sum',        'sum(${1:iterable})',                       'Sum all elements'),
            fn('min',        'min(${1:iterable})',                       'Return minimum value'),
            fn('max',        'max(${1:iterable})',                       'Return maximum value'),
            fn('abs',        'abs(${1:x})',                              'Return absolute value'),
            fn('round',      'round(${1:x}, ${2:ndigits})',              'Round to n decimal places'),
            fn('open',       'open(${1:"file"}, ${2:"r"})',              'Open a file'),
            fn('super',      'super()',                                   'Get the parent class proxy'),
            fn('property',   'property(${0})',                           'Create a property descriptor'),
            fn('staticmethod','staticmethod(${0})',                      'Mark a method as static'),
            fn('classmethod', 'classmethod(${0})',                       'Mark a method as a classmethod'),
        ];
    }

    // ── self.* Scene methods ──────────────────────────────────────────────────
    function selfItems(range) {
        const m = (label, snippet, doc) => ({
            label, kind: K.Method, range,
            insertText: snippet,
            insertTextRules: SNIP,
            documentation: doc || '',
            detail: 'Scene method',
        });
        return [
            m('play',                       'play(${1:animation})',                                            'Play one or more animations'),
            m('wait',                       'wait(${1:1})',                                                    'Pause for a duration (default 1 second)'),
            m('add',                        'add(${1:mobject})',                                               'Add mobject(s) to the scene'),
            m('remove',                     'remove(${1:mobject})',                                            'Remove mobject(s) from the scene'),
            m('clear',                      'clear()',                                                         'Remove all mobjects from the scene'),
            m('bring_to_front',             'bring_to_front(${1:mobject})',                                    'Move mobject to front of render order'),
            m('bring_to_back',              'bring_to_back(${1:mobject})',                                     'Move mobject to back of render order'),
            m('add_updater',                'add_updater(${1:func})',                                          'Add a scene updater function'),
            m('remove_updater',             'remove_updater(${1:func})',                                       'Remove a scene updater function'),
            m('get_top_level_mobjects',     'get_top_level_mobjects()',                                        'Get list of all top-level scene mobjects'),
            m('set_camera_orientation',     'set_camera_orientation(phi=${1:75 * DEGREES}, theta=${2:-45 * DEGREES})', 'Set 3D camera orientation (ThreeDScene)'),
            m('move_camera',                'move_camera(phi=${1:0}, theta=${2:0})',                           'Animate 3D camera movement (ThreeDScene)'),
            m('begin_ambient_camera_rotation','begin_ambient_camera_rotation(rate=${1:0.02})',                 'Start slow camera rotation (ThreeDScene)'),
            m('stop_ambient_camera_rotation','stop_ambient_camera_rotation()',                                 'Stop ambient camera rotation (ThreeDScene)'),
            m('next_section',               'next_section(${1:"name"})',                                       'Create a new video section'),
            m('pause',                      'pause()',                                                         'Pause the animation'),
        ];
    }

    // ── Manim Scene types ────────────────────────────────────────────────────
    function sceneItems(range) {
        const s = (label, doc) => ({
            label, kind: K.Class, range,
            insertText: label,
            documentation: doc || '',
            detail: 'Manim Scene',
        });
        return [
            s('Scene',                      'Base class for all 2D Manim scenes. Override construct(self) to define your animation.'),
            s('ThreeDScene',                '3D scene with a perspective camera. Use set_camera_orientation() and move_camera().'),
            s('MovingCameraScene',          'Scene where the camera can be moved and zoomed programmatically.'),
            s('ZoomedScene',                'Scene that supports a zoomed display window alongside the main scene.'),
            s('VectorScene',                'Scene designed for vector field visualizations.'),
            s('LinearTransformationScene',  'Scene optimized for illustrating linear algebra transformations.'),
        ];
    }

    // ── Manim Animations ─────────────────────────────────────────────────────
    function animItems(range) {
        const a = (label, snippet, doc) => ({
            label, kind: K.Function, range,
            insertText: snippet || (label + '(${0})'),
            insertTextRules: SNIP,
            documentation: doc || '',
            detail: 'Manim Animation',
        });
        return [
            a('Create',                 'Create(${1:mobject})',                          'Animate drawing/creation of a mobject'),
            a('Uncreate',               'Uncreate(${1:mobject})',                        'Reverse of Create — un-draw a mobject'),
            a('Write',                  'Write(${1:mobject})',                           'Write text or draw strokes of a mobject'),
            a('Unwrite',                'Unwrite(${1:mobject})',                         'Reverse of Write'),
            a('FadeIn',                 'FadeIn(${1:mobject})',                          'Fade a mobject into view'),
            a('FadeOut',                'FadeOut(${1:mobject})',                         'Fade a mobject out of view'),
            a('FadeTransform',          'FadeTransform(${1:source}, ${2:target})',       'Fade source out and target in'),
            a('Transform',              'Transform(${1:source}, ${2:target})',           'Morph one mobject into another'),
            a('ReplacementTransform',   'ReplacementTransform(${1:source}, ${2:target})','Transform and replace source with target in the scene'),
            a('TransformFromCopy',      'TransformFromCopy(${1:source}, ${2:target})',   'Transform a copy of source into target'),
            a('ClockwiseTransform',     'ClockwiseTransform(${1:source}, ${2:target})',  'Transform rotating clockwise'),
            a('CounterclockwiseTransform','CounterclockwiseTransform(${1:source}, ${2:target})','Transform rotating counterclockwise'),
            a('MoveToTarget',           'MoveToTarget(${1:mobject})',                    'Move mobject to its saved .target position'),
            a('GrowFromCenter',         'GrowFromCenter(${1:mobject})',                  'Grow a mobject from its center'),
            a('GrowArrow',              'GrowArrow(${1:arrow})',                         'Grow an arrow from its tail to tip'),
            a('GrowFromPoint',          'GrowFromPoint(${1:mobject}, ${2:point})',       'Grow a mobject from a specific point'),
            a('GrowFromEdge',           'GrowFromEdge(${1:mobject}, ${2:edge})',         'Grow a mobject from a specific edge'),
            a('ShrinkToCenter',         'ShrinkToCenter(${1:mobject})',                  'Shrink mobject down to its center'),
            a('Rotate',                 'Rotate(${1:mobject}, ${2:angle})',              'Rotate a mobject by an angle'),
            a('ScaleInPlace',           'ScaleInPlace(${1:mobject}, ${2:scale_factor})', 'Scale a mobject in place'),
            a('Flash',                  'Flash(${1:point})',                             'Flash animation at a point'),
            a('Circumscribe',           'Circumscribe(${1:mobject})',                    'Draw a shape around a mobject'),
            a('Indicate',               'Indicate(${1:mobject})',                        'Scale and flash a mobject to indicate it'),
            a('Wiggle',                 'Wiggle(${1:mobject})',                          'Wiggle a mobject'),
            a('ShowCreation',           'ShowCreation(${1:mobject})',                    'Alias for Create (legacy name)'),
            a('DrawBorderThenFill',     'DrawBorderThenFill(${1:mobject})',              'Draw border then fill the mobject'),
            a('SpinInFromNothing',      'SpinInFromNothing(${1:mobject})',               'Spin and scale mobject in from nothing'),
            a('ShowPassingFlash',       'ShowPassingFlash(${1:mobject})',                'Show a flash passing along a path'),
            a('ShowPassingFlashAround', 'ShowPassingFlashAround(${1:mobject})',          'Passing flash that travels around a mobject'),
            a('ShowCreationThenFadeOut','ShowCreationThenFadeOut(${1:mobject})',         'Create then fade out a mobject'),
            a('FadeToColor',            'FadeToColor(${1:mobject}, ${2:color})',         'Animate color change'),
            a('MoveAlongPath',          'MoveAlongPath(${1:mobject}, ${2:path})',        'Move mobject along a VMobject path'),
            a('Homotopy',               'Homotopy(${1:func}, ${2:mobject})',             'Apply a homotopy transformation'),
            a('AnimationGroup',         'AnimationGroup(${1:anim1}, ${2:anim2})',        'Run animations in parallel'),
            a('Succession',             'Succession(${1:anim1}, ${2:anim2})',            'Run animations in sequence one after another'),
            a('LaggedStart',            'LaggedStart(${1:anim1}, ${2:anim2})',           'Start animations with a lag between each'),
            a('LaggedStartMap',         'LaggedStartMap(${1:AnimClass}, ${2:mobjects})', 'Apply an animation to a group with lag'),
            a('Wait',                   'Wait(${1:1})',                                  'Wait animation (duration in seconds)'),
            a('ApplyMethod',            'ApplyMethod(${1:mobject.method}, ${2:args})',   'Animate a method call as an animation'),
            a('ApplyFunction',          'ApplyFunction(${1:func}, ${2:mobject})',        'Apply a function to every point of a mobject'),
            a('ApplyMatrix',            'ApplyMatrix(${1:matrix}, ${2:mobject})',        'Apply a matrix transformation'),
            a('AddTextLetterByLetter',  'AddTextLetterByLetter(${1:text})',              'Animate adding text one character at a time'),
            a('RemoveTextLetterByLetter','RemoveTextLetterByLetter(${1:text})',          'Remove text one character at a time'),
        ];
    }

    // ── Manim Mobjects ────────────────────────────────────────────────────────
    function mobjectItems(range) {
        const mo = (label, snippet, doc) => ({
            label, kind: K.Class, range,
            insertText: snippet || (label + '(${0})'),
            insertTextRules: SNIP,
            documentation: doc || '',
            detail: 'Manim Mobject',
        });
        return [
            // ─ Shapes
            mo('Circle',                'Circle(radius=${1:1})',                                   'Create a circle'),
            mo('Square',                'Square(side_length=${1:2})',                              'Create a square'),
            mo('Rectangle',             'Rectangle(width=${1:4}, height=${2:2})',                  'Create a rectangle'),
            mo('Triangle',              'Triangle()',                                              'Create an equilateral triangle'),
            mo('Polygon',               'Polygon(${1:v1, v2, v3})',                               'Create a polygon from vertices'),
            mo('RegularPolygon',        'RegularPolygon(n=${1:6})',                               'Create a regular n-sided polygon'),
            mo('Star',                  'Star(n=${1:5})',                                         'Create a star shape with n points'),
            mo('Arc',                   'Arc(radius=${1:1}, start_angle=${2:0}, angle=${3:TAU})', 'Create an arc'),
            mo('ArcBetweenPoints',      'ArcBetweenPoints(${1:start}, ${2:end})',                 'Arc connecting two points'),
            mo('Ellipse',               'Ellipse(width=${1:4}, height=${2:2})',                   'Create an ellipse'),
            mo('Annulus',               'Annulus(inner_radius=${1:1}, outer_radius=${2:2})',      'Create a ring (annulus)'),
            mo('Sector',                'Sector(outer_radius=${1:1}, angle=${2:TAU / 4})',        'Create a sector (pie slice)'),
            mo('RoundedRectangle',      'RoundedRectangle(width=${1:4}, height=${2:2}, corner_radius=${3:0.5})', 'Rectangle with rounded corners'),
            // ─ Lines & arrows
            mo('Line',                  'Line(${1:start}, ${2:end})',                              'Create a line segment'),
            mo('DashedLine',            'DashedLine(${1:start}, ${2:end})',                        'Create a dashed line'),
            mo('Arrow',                 'Arrow(${1:start}, ${2:end})',                             'Create an arrow'),
            mo('DoubleArrow',           'DoubleArrow(${1:start}, ${2:end})',                       'Create a double-headed arrow'),
            mo('Vector',                'Vector(${1:direction})',                                  'Arrow from ORIGIN in a given direction'),
            mo('CurvedArrow',           'CurvedArrow(${1:start}, ${2:end})',                       'Create a curved arrow'),
            mo('CurvedDoubleArrow',     'CurvedDoubleArrow(${1:start}, ${2:end})',                 'Curved arrow with heads at both ends'),
            mo('Brace',                 'Brace(${1:mobject}, direction=${2:DOWN})',                'Curly brace around a mobject'),
            mo('BraceLabel',            'BraceLabel(${1:mobject}, ${2:"label"})',                  'Brace with a text label'),
            mo('BraceBetweenPoints',    'BraceBetweenPoints(${1:p1}, ${2:p2})',                    'Brace between two points'),
            mo('SurroundingRectangle',  'SurroundingRectangle(${1:mobject})',                      'Rectangle that tightly surrounds a mobject'),
            mo('BackgroundRectangle',   'BackgroundRectangle(${1:mobject})',                       'Filled background rectangle behind a mobject'),
            mo('Underline',             'Underline(${1:mobject})',                                 'Underline below a mobject'),
            mo('Cross',                 'Cross(${1:mobject})',                                     'Draw an X cross through a mobject'),
            // ─ Points
            mo('Dot',                   'Dot(${1:ORIGIN})',                                        'Create a small filled dot'),
            mo('SmallDot',              'SmallDot(${1:ORIGIN})',                                   'Create a very small dot'),
            mo('AnnotationDot',         'AnnotationDot()',                                         'Dot styled for annotations'),
            mo('Point',                 'Point(${1:location})',                                    'An invisible point (no visual)'),
            // ─ Graphs & axes
            mo('NumberLine',            'NumberLine(x_range=[${1:-5}, ${2:5}, ${3:1}])',          'Create a number line'),
            mo('Axes',                  'Axes(\n\tx_range=[${1:-5}, ${2:5}, ${3:1}],\n\ty_range=[${4:-5}, ${5:5}, ${6:1}]\n)', 'Create 2D axes'),
            mo('ThreeDAxes',            'ThreeDAxes()',                                            'Create 3D axes'),
            mo('NumberPlane',           'NumberPlane()',                                           'Create a coordinate plane with grid'),
            mo('ComplexPlane',          'ComplexPlane()',                                           'Coordinate plane for complex numbers'),
            mo('PolarPlane',            'PolarPlane()',                                            'Polar coordinate plane'),
            // ─ Text
            mo('Text',                  'Text(${1:"Hello"})',                                      'Render text using Pango (no LaTeX required)'),
            mo('Tex',                   'Tex(${1:"\\\\LaTeX"})',                                   'Render LaTeX text (text mode)'),
            mo('MathTex',               'MathTex(${1:"x^2"})',                                    'Render LaTeX math expression'),
            mo('Title',                 'Title(${1:"Title"})',                                     'Large centered title text'),
            mo('Paragraph',             'Paragraph(${1:"Line 1", "Line 2"})',                      'Multi-line paragraph'),
            mo('BulletedList',          'BulletedList(${1:"Item 1", "Item 2"})',                   'Bulleted list of text items'),
            mo('Code',                  'Code(${1:"code.py"}, language=${2:"python"})',            'Display code with syntax highlighting'),
            mo('MarkupText',            'MarkupText(${1:"<b>bold</b>"})',                          'Text with Pango markup (bold, color, etc.)'),
            // ─ Math
            mo('Matrix',                'Matrix([[${1:1, 0}], [${2:0, 1}]])',                     'Display a matrix'),
            mo('MobjectMatrix',         'MobjectMatrix(${1:[[mob1, mob2]]})',                      'Matrix of mobjects'),
            mo('DecimalNumber',         'DecimalNumber(${1:0})',                                   'Displayable decimal number'),
            mo('Integer',               'Integer(${1:0})',                                         'Displayable integer'),
            mo('Variable',              'Variable(${1:1}, ${2:"x"})',                             'Labeled variable that can be animated'),
            mo('ValueTracker',          'ValueTracker(${1:0})',                                    'Tracks a numeric value; use .animate.set_value()'),
            // ─ Groups
            mo('VGroup',                'VGroup(${1:mob1, mob2})',                                 'Group multiple VMobjects together'),
            mo('HGroup',                'HGroup(${1:mob1, mob2})',                                 'Arrange mobjects horizontally'),
            mo('VDict',                 'VDict({"${1:key}": ${2:mobject}})',                       'Dictionary-keyed group of VMobjects'),
            mo('Group',                 'Group(${1:mob1, mob2})',                                  'Group any mobjects (including non-VM)'),
        ];
    }

    // ── Manim colors ──────────────────────────────────────────────────────────
    function colorItems(range) {
        const c = (label, hex) => ({
            label, kind: K.Color, range,
            insertText: label,
            documentation: hex ? `Hex: ${hex}` : '',
            detail: 'Manim color',
        });
        return [
            c('WHITE',        '#FFFFFF'), c('BLACK',        '#000000'),
            c('GRAY',         '#888888'), c('GREY',         '#888888'),
            c('DARK_GRAY',    '#444444'), c('DARK_GREY',    '#444444'),
            c('LIGHT_GRAY',   '#BBBBBB'), c('LIGHT_GREY',   '#BBBBBB'),
            c('DARKER_GRAY',  '#222222'), c('LIGHTER_GRAY', '#DDDDDD'),
            c('RED',          '#FC6255'),
            c('RED_A',        '#F7A1A3'), c('RED_B', '#FF8080'), c('RED_C', '#FC6255'),
            c('RED_D',        '#E65A4C'), c('RED_E', '#CF5044'),
            c('BLUE',         '#58C4DD'),
            c('BLUE_A',       '#C7E9F1'), c('BLUE_B', '#9CDCEB'), c('BLUE_C', '#58C4DD'),
            c('BLUE_D',       '#29ABCA'), c('BLUE_E', '#236B8E'),
            c('GREEN',        '#83C167'),
            c('GREEN_A',      '#C9E2AE'), c('GREEN_B', '#A6CF8C'), c('GREEN_C', '#83C167'),
            c('GREEN_D',      '#77B05D'), c('GREEN_E', '#699C52'),
            c('YELLOW',       '#FFFF00'),
            c('YELLOW_A',     '#FFF1B6'), c('YELLOW_B', '#FFEA94'), c('YELLOW_C', '#FFFF00'),
            c('YELLOW_D',     '#F4D345'), c('YELLOW_E', '#E8C11C'),
            c('ORANGE',       '#FF862F'),
            c('GOLD',         '#C89F5D'),
            c('GOLD_A',       '#F7C797'), c('GOLD_B', '#F9B775'), c('GOLD_C', '#F0AC5F'),
            c('GOLD_D',       '#E1A158'), c('GOLD_E', '#C78D46'),
            c('TEAL',         '#5CD0B3'),
            c('TEAL_A',       '#ACEAD7'), c('TEAL_B', '#76DDC0'), c('TEAL_C', '#5CD0B3'),
            c('TEAL_D',       '#55C1A7'), c('TEAL_E', '#49A88F'),
            c('MAROON',       '#C55F73'),
            c('MAROON_A',     '#EAA0A4'), c('MAROON_B', '#CF7C8F'), c('MAROON_C', '#C55F73'),
            c('MAROON_D',     '#A24D61'), c('MAROON_E', '#94424F'),
            c('PURPLE',       '#9A72AC'),
            c('PURPLE_A',     '#CAA3E8'), c('PURPLE_B', '#B189C6'), c('PURPLE_C', '#9A72AC'),
            c('PURPLE_D',     '#715582'), c('PURPLE_E', '#644172'),
            c('PINK',         '#D147BD'), c('LIGHT_PINK',  '#DC75CD'),
            c('DARK_BROWN',   '#736357'), c('LIGHT_BROWN', '#CD853F'),
            c('PURE_RED',     '#FF0000'), c('PURE_GREEN',  '#00FF00'), c('PURE_BLUE', '#0000FF'),
        ];
    }

    // ── Manim direction/math constants ────────────────────────────────────────
    function constItems(range) {
        const ct = (label, doc) => ({
            label, kind: K.Constant, range,
            insertText: label,
            documentation: doc || '',
            detail: 'Manim constant',
        });
        return [
            ct('UP',     'Unit vector up     → [0, 1, 0]'),
            ct('DOWN',   'Unit vector down   → [0, -1, 0]'),
            ct('LEFT',   'Unit vector left   → [-1, 0, 0]'),
            ct('RIGHT',  'Unit vector right  → [1, 0, 0]'),
            ct('ORIGIN', 'Scene origin       → [0, 0, 0]'),
            ct('UL',     'Upper-left  corner direction'),
            ct('UR',     'Upper-right corner direction'),
            ct('DL',     'Lower-left  corner direction'),
            ct('DR',     'Lower-right corner direction'),
            ct('IN',     'Into the screen    → [0, 0, -1]  (3D)'),
            ct('OUT',    'Out of the screen  → [0, 0, 1]   (3D)'),
            ct('PI',     'π ≈ 3.14159'),
            ct('TAU',    'τ = 2π ≈ 6.28318  (full rotation)'),
            ct('DEGREES','π/180 — multiply degrees by DEGREES to get radians: 45 * DEGREES'),
        ];
    }

    // ── 'from manim import *' shortcut ────────────────────────────────────────
    function importShortcut(range) {
        return [{
            label:           'from manim import *',
            kind:            K.Module,
            insertText:      'from manim import *',
            documentation:   'Standard Manim wildcard import',
            detail:          'Manim',
            range,
        }];
    }

    // ── Main completion provider ──────────────────────────────────────────────
    monaco.languages.registerCompletionItemProvider('python', {
        triggerCharacters: ['.', ' ', '(', ','],

        provideCompletionItems(model, position) {
            const range  = mkRange(model, position);
            const prefix = linePrefix(model, position);

            // ─ After 'self.'  →  only scene methods
            if (/\bself\.$/.test(prefix)) {
                return { suggestions: selfItems(range) };
            }

            // ─ After 'from manim import …'  →  only Manim symbols
            if (/\bfrom\s+manim\s+import\s+\w*$/.test(prefix + model.getWordUntilPosition(position).word)) {
                return {
                    suggestions: [
                        ...sceneItems(range),
                        ...animItems(range),
                        ...mobjectItems(range),
                        ...colorItems(range),
                        ...constItems(range),
                    ],
                };
            }

            // ─ General  →  everything
            return {
                suggestions: [
                    ...kwItems(range),
                    ...builtinItems(range),
                    ...importShortcut(range),
                    ...sceneItems(range),
                    ...animItems(range),
                    ...mobjectItems(range),
                    ...colorItems(range),
                    ...constItems(range),
                ],
            };
        },
    });

    // ── Narration completion (built-in feature) ──────────────────────────────
    // Shows narrate() snippet for Kokoro TTS narration.
    monaco.languages.registerCompletionItemProvider('python', {
        triggerCharacters: ['n'],

        provideCompletionItems(model, position) {
            const line   = model.getLineContent(position.lineNumber);
            const before = line.substring(0, position.column - 1);

            // Trigger when typing narrate at start-of-line / after whitespace
            if (/^\s*n$/i.test(before) || /^\s*na/i.test(before) || /^\s*narr/i.test(before)) {
                return {
                    suggestions: [{
                        label:           'narrate',
                        kind:            K.Snippet,
                        insertText:      'narrate("${0:Your narration text}")',
                        insertTextRules: SNIP,
                        documentation:   'Add TTS narration. Text in quotes will be spoken by Kokoro TTS and merged with the rendered video.',
                        detail:          'Narration (Kokoro TTS)',
                        sortText:        '0_narrate',
                        filterText:      'narrate narration',
                        range: {
                            startLineNumber: position.lineNumber,
                            endLineNumber:   position.lineNumber,
                            startColumn:     Math.max(1, position.column - before.trimStart().length),
                            endColumn:       position.column,
                        },
                    }],
                };
            }
            return null;
        },
    });

    // ── Hover provider ────────────────────────────────────────────────────────
    const HOVER_DOCS = {
        Scene:                   '**Scene** — Base 2D scene. Override `construct(self)` to build your animation.',
        ThreeDScene:             '**ThreeDScene** — 3D perspective scene. Use `set_camera_orientation()` and `move_camera()`.',
        MovingCameraScene:       '**MovingCameraScene** — Scene whose camera can move and zoom.',
        ZoomedScene:             '**ZoomedScene** — Shows a zoomed inset alongside the main view.',
        VGroup:                  '**VGroup(*mobjects)** — Group of VMobjects that can be manipulated together.',
        AnimationGroup:          '**AnimationGroup(*animations, lag_ratio=0)** — Run multiple animations simultaneously.',
        Succession:              '**Succession(*animations)** — Run animations one after another.',
        LaggedStart:             '**LaggedStart(*animations, lag_ratio=0.05)** — Start each animation slightly after the previous.',
        Create:                  '**Create(mobject)** — Animate drawing the outline and fill of a mobject.',
        Write:                   '**Write(mobject)** — Animate writing text or a path stroke by stroke.',
        Transform:               '**Transform(source, target)** — Morph source into target. Source stays in scene.',
        ReplacementTransform:    '**ReplacementTransform(source, target)** — Morph source into target, replacing source.',
        FadeIn:                  '**FadeIn(mobject, shift=ORIGIN)** — Fade into view with optional directional shift.',
        FadeOut:                 '**FadeOut(mobject, shift=ORIGIN)** — Fade out with optional directional shift.',
        MathTex:                 '**MathTex(*strings)** — LaTeX math mode. Strings are joined and wrapped in `$$`.',
        Text:                    '**Text(text, font_size=48, color=WHITE)** — Pango-rendered text (no LaTeX).',
        Tex:                     '**Tex(*strings)** — LaTeX text mode (use for prose with occasional math).',
        ValueTracker:            '**ValueTracker(value=0)** — Holds a numeric value. Use `.get_value()` / `.set_value()`, or `.animate.set_value()` for smooth transitions.',
        NumberPlane:             '**NumberPlane()** — Full coordinate plane with labeled axes and grid.',
        Axes:                    '**Axes(x_range, y_range)** — Pair of axes for plotting.',
        UP:                      '**UP** = `np.array([0, 1, 0])` — Unit vector pointing up.',
        DOWN:                    '**DOWN** = `np.array([0, -1, 0])` — Unit vector pointing down.',
        LEFT:                    '**LEFT** = `np.array([-1, 0, 0])` — Unit vector pointing left.',
        RIGHT:                   '**RIGHT** = `np.array([1, 0, 0])` — Unit vector pointing right.',
        ORIGIN:                  '**ORIGIN** = `np.array([0, 0, 0])` — Center of the scene.',
        TAU:                     '**TAU** = 2π ≈ 6.28318. Full rotation in radians. Alias for `2 * PI`.',
        DEGREES:                 '**DEGREES** = π/180. Multiply degrees by DEGREES: `angle = 45 * DEGREES`.',
        PI:                      '**PI** ≈ 3.14159265...',
        WHITE:                   'Manim color: #FFFFFF',
        BLACK:                   'Manim color: #000000',
        RED:                     'Manim color: #FC6255',
        BLUE:                    'Manim color: #58C4DD',
        GREEN:                   'Manim color: #83C167',
        YELLOW:                  'Manim color: #FFFF00',
        ORANGE:                  'Manim color: #FF862F',
        PURPLE:                  'Manim color: #9A72AC',
        TEAL:                    'Manim color: #5CD0B3',
        GOLD:                    'Manim color: #C89F5D',
        PINK:                    'Manim color: #D147BD',
        Indicate:                '**Indicate(mobject)** — Briefly scale up and change color to draw attention.',
        Circumscribe:            '**Circumscribe(mobject)** — Draw a shape around the mobject then fade it.',
        Flash:                   '**Flash(point, color=YELLOW)** — Radial flash lines at a point.',
        SurroundingRectangle:    '**SurroundingRectangle(mobject)** — Tight rectangle that fits around a mobject.',
        Brace:                   '**Brace(mobject, direction=DOWN)** — Curly brace. Use .get_tip() to position a label.',
    };

    monaco.languages.registerHoverProvider('python', {
        provideHover(model, position) {
            const word = model.getWordAtPosition(position);
            if (!word) return null;
            const doc = HOVER_DOCS[word.word];
            if (!doc) return null;
            return {
                range: new monaco.Range(
                    position.lineNumber, word.startColumn,
                    position.lineNumber, word.endColumn
                ),
                contents: [{ value: doc }],
            };
        },
    });

    // ── Signature help (parameter hints) ─────────────────────────────────────
    // Fires immediately on '(' or ',' — zero lag, no LSP needed.
    // When basedpyright also initialises it takes over with even richer data.

    // ── helpers for rich param objects ────────────────────────────────────────
    // p(label, doc) creates a {label, doc} param — shown individually in tooltip
    const p = (label, doc) => ({ label, doc });

    const SIG_DB = {
        // ── Python builtins ────────────────────────────────────────────────
        range: [
            {
                label: 'range(stop: int) -> range',
                doc: '**range(stop)** `-> range`\n\nReturn an immutable sequence of integers `0, 1, …, stop−1`.\n\n```python\nfor i in range(5):      # 0 1 2 3 4\nlist(range(10))         # [0,1,2,...,9]\n```',
                params: [p('stop: int', '**stop** `int`\n\nUpper bound (exclusive). The sequence ends at `stop − 1`.')],
            },
            {
                label: 'range(start: int, stop: int, step: int = 1) -> range',
                doc: '**range(start, stop, step)** `-> range`\n\nReturn integers from `start` up to (but not including) `stop`, incrementing by `step`.\n\n```python\nrange(2, 10, 2)   # 2 4 6 8\nrange(10, 0, -1)  # 10 9 8 … 1\n```',
                params: [
                    p('start: int',     '**start** `int`\n\nFirst value in the sequence.'),
                    p('stop: int',      '**stop** `int`\n\nUpper bound (exclusive).'),
                    p('step: int = 1',  '**step** `int` *(default: `1`)*\n\nIncrement between each value. Use a negative value to count down.'),
                ],
            },
        ],
        print: [{
            label: 'print(*objects, sep=" ", end="\\n", file=sys.stdout, flush=False) -> None',
            doc: '**print** `-> None`\n\nPrint `objects` to a text stream, separated by `sep` and followed by `end`.\n\n```python\nprint("x =", x)              # x = 42\nprint(1, 2, 3, sep=", ")     # 1, 2, 3\nprint("no newline", end="")  # stays on same line\n```',
            params: [
                p('*objects',          '**objects**\n\nZero or more objects to print. Non-strings are converted with `str()`.'),
                p('sep: str = " "',    '**sep** `str` *(default: `" "`)*\n\nString inserted between values.'),
                p('end: str = "\\n"',  '**end** `str` *(default: `"\\n"`)*\n\nString appended after the last value.'),
                p('file = sys.stdout', '**file**\n\nFile-like object to write to. Defaults to `sys.stdout`.'),
                p('flush: bool = False','**flush** `bool` *(default: `False`)*\n\nIf `True`, force-flush the stream after printing.'),
            ],
        }],
        len: [{
            label: 'len(obj) -> int',
            doc: '**len** `-> int`\n\nReturn the number of items in a container.\n\n```python\nlen([1, 2, 3])   # 3\nlen("hello")     # 5\nlen({})          # 0\n```',
            params: [p('obj', '**obj**\n\nAny sequence, collection, or object that implements `__len__`.')],
        }],
        enumerate: [{
            label: 'enumerate(iterable: Iterable, start: int = 0) -> Iterator[tuple[int, T]]',
            doc: '**enumerate** `-> Iterator[tuple[int, T]]`\n\nWrap an iterable and yield `(index, value)` pairs.\n\n```python\nfor i, v in enumerate(["a","b","c"]):\n    print(i, v)   # 0 a  /  1 b  /  2 c\nenumerate(items, start=1)  # index from 1\n```',
            params: [
                p('iterable: Iterable', '**iterable** `Iterable`\n\nAny iterable to index over.'),
                p('start: int = 0',     '**start** `int` *(default: `0`)*\n\nFirst index value. Use `start=1` to count from one.'),
            ],
        }],
        zip: [{
            label: 'zip(*iterables: Iterable) -> Iterator[tuple]',
            doc: '**zip** `-> Iterator[tuple]`\n\nPair up elements from each iterable, stopping at the shortest.\n\n```python\nlist(zip([1,2,3], ["a","b","c"]))  # [(1,"a"),(2,"b"),(3,"c")]\nfor x, y in zip(xs, ys): ...\n```',
            params: [p('*iterables: Iterable', '**iterables** `Iterable`\n\nTwo or more iterables to zip together.')],
        }],
        map: [{
            label: 'map(function: Callable, *iterables: Iterable) -> Iterator',
            doc: '**map** `-> Iterator`\n\nApply `function` to every item and return a lazy iterator.\n\n```python\nlist(map(str, [1, 2, 3]))        # ["1","2","3"]\nlist(map(abs, [-1, -2, 3]))      # [1, 2, 3]\nlist(map(pow, [2,3], [3,2]))     # [8, 9]\n```',
            params: [
                p('function: Callable', '**function** `Callable`\n\nFunction to apply to each element.'),
                p('*iterables: Iterable','**iterables** `Iterable`\n\nOne or more iterables. If multiple, `function` receives one arg per iterable.'),
            ],
        }],
        filter: [{
            label: 'filter(function: Callable | None, iterable: Iterable) -> Iterator',
            doc: '**filter** `-> Iterator`\n\nKeep elements where `function(element)` is truthy.\n\n```python\nlist(filter(None, [0,1,"",2]))      # [1, 2]  (falsy removed)\nlist(filter(str.isupper, "aAbBcC")) # ["A","B","C"]\n```',
            params: [
                p('function: Callable | None', '**function** `Callable | None`\n\nPredicate function. Pass `None` to remove falsy values.'),
                p('iterable: Iterable',        '**iterable** `Iterable`\n\nThe sequence to filter.'),
            ],
        }],
        sorted: [{
            label: 'sorted(iterable: Iterable, *, key: Callable = None, reverse: bool = False) -> list',
            doc: '**sorted** `-> list`\n\nReturn a new sorted list. Does not modify the original.\n\n```python\nsorted([3,1,2])                     # [1,2,3]\nsorted(words, key=str.lower)        # case-insensitive\nsorted(nums, reverse=True)          # descending\nsorted(data, key=lambda x: x.age)  # by attribute\n```',
            params: [
                p('iterable: Iterable',     '**iterable** `Iterable`\n\nThe sequence to sort.'),
                p('key: Callable = None',   '**key** `Callable` *(optional)*\n\nOne-argument function used to extract a comparison key.\nExample: `key=str.lower`, `key=lambda x: x[1]`'),
                p('reverse: bool = False',  '**reverse** `bool` *(default: `False`)*\n\nIf `True`, sort in descending (largest-first) order.'),
            ],
        }],
        min: [
            {
                label: 'min(iterable: Iterable, *, key: Callable = None, default=...) -> T',
                doc: '**min** `-> T`\n\nReturn the smallest item in an iterable or among positional arguments.\n\n```python\nmin([3, 1, 2])            # 1\nmin("cat", "ant", "bat")  # "ant"\nmin([], default=0)        # 0  (avoids ValueError)\nmin(data, key=lambda x: x.value)\n```',
                params: [
                    p('iterable: Iterable',    '**iterable** `Iterable`\n\nThe sequence to search.'),
                    p('key: Callable = None',  '**key** `Callable` *(optional)*\n\nOne-argument key function for comparison.'),
                    p('default = ...',         '**default** *(optional)*\n\nReturn this value if the iterable is empty (avoids `ValueError`).'),
                ],
            },
            {
                label: 'min(arg1, arg2, *args, key: Callable = None) -> T',
                doc: '**min** with positional arguments.',
                params: [
                    p('arg1',                 '**arg1** — First value to compare.'),
                    p('arg2',                 '**arg2** — Second value to compare.'),
                    p('*args',                '**args** — Additional values.'),
                    p('key: Callable = None', '**key** *(optional)* — Comparison key function.'),
                ],
            },
        ],
        max: [
            {
                label: 'max(iterable: Iterable, *, key: Callable = None, default=...) -> T',
                doc: '**max** `-> T`\n\nReturn the largest item.\n\n```python\nmax([3, 1, 2])           # 3\nmax(data, key=len)       # longest item\nmax([], default=-1)      # -1\n```',
                params: [
                    p('iterable: Iterable',   '**iterable** `Iterable`\n\nThe sequence to search.'),
                    p('key: Callable = None', '**key** *(optional)* — Comparison key function.'),
                    p('default = ...',        '**default** *(optional)* — Returned if iterable is empty.'),
                ],
            },
            {
                label: 'max(arg1, arg2, *args, key: Callable = None) -> T',
                doc: '**max** with positional arguments.',
                params: [
                    p('arg1', '**arg1** — First value.'), p('arg2', '**arg2** — Second value.'),
                    p('*args','**args** — Additional values.'), p('key: Callable = None','**key** *(optional)*.'),
                ],
            },
        ],
        sum: [{
            label: 'sum(iterable: Iterable[N], start: N = 0) -> N',
            doc: '**sum** `-> N`\n\nReturn the sum of all items, starting from `start`.\n\n```python\nsum([1,2,3])         # 6\nsum([1,2,3], 10)     # 16\nsum(x**2 for x in range(5))  # 30\n```',
            params: [
                p('iterable: Iterable[N]', '**iterable** `Iterable[N]`\n\nNumbers to add together.'),
                p('start: N = 0',          '**start** `N` *(default: `0`)*\n\nInitial value added to the total.'),
            ],
        }],
        abs: [{
            label: 'abs(x: int | float | complex) -> int | float',
            doc: '**abs** `-> int | float`\n\nReturn the absolute value of a number.\n\n```python\nabs(-5)    # 5\nabs(-3.7)  # 3.7\nabs(3+4j)  # 5.0  (magnitude of complex)\n```',
            params: [p('x: int | float | complex', '**x** `int | float | complex`\n\nThe number to take the absolute value of.')],
        }],
        round: [{
            label: 'round(number: float, ndigits: int = None) -> int | float',
            doc: '**round** `-> int | float`\n\nRound a number to `ndigits` decimal places (banker\'s rounding).\n\n```python\nround(3.14159, 2)  # 3.14\nround(2.5)         # 2  (banker\'s rounding → nearest even)\nround(123, -1)     # 120\n```',
            params: [
                p('number: float',      '**number** `float`\n\nThe number to round.'),
                p('ndigits: int = None','**ndigits** `int` *(optional)*\n\nDecimal places. Omit for integer result. Negative rounds left of decimal.'),
            ],
        }],
        int: [{
            label: 'int(x: str | float = 0, base: int = 10) -> int',
            doc: '**int** `-> int`\n\nConvert a number or string to an integer.\n\n```python\nint(3.9)       # 3  (truncates, not rounds)\nint("42")      # 42\nint("0xFF",16) # 255\nint("0b1010",2)# 10\n```',
            params: [
                p('x: str | float = 0', '**x** `str | float` *(default: `0`)*\n\nValue to convert. Strings with binary/hex/octal prefix work when `base` matches.'),
                p('base: int = 10',     '**base** `int` *(default: `10`)*\n\nNumeric base for string conversion. Use `0` to auto-detect from prefix (`0x`, `0b`, `0o`).'),
            ],
        }],
        float: [{
            label: 'float(x: str | int = 0.0) -> float',
            doc: '**float** `-> float`\n\nConvert to a floating-point number.\n\n```python\nfloat(3)      # 3.0\nfloat("3.14") # 3.14\nfloat("inf")  # inf\nfloat("nan")  # nan\n```',
            params: [p('x: str | int = 0.0', '**x** `str | int` *(default: `0.0`)*\n\nValue to convert. Accepts numeric strings including `"inf"` and `"nan"`.')],
        }],
        str: [{
            label: 'str(object: object = "") -> str',
            doc: '**str** `-> str`\n\nReturn a string representation of `object`.\n\n```python\nstr(42)       # "42"\nstr(3.14)     # "3.14"\nstr(True)     # "True"\nstr([1,2,3])  # "[1, 2, 3]"\n```',
            params: [p('object: object = ""', '**object** *(default: `""`)*\n\nConverted using `object.__str__()`. For a developer representation, use `repr(object)`.')],
        }],
        list: [{
            label: 'list(iterable: Iterable = ()) -> list',
            doc: '**list** `-> list`\n\nCreate a new list from an iterable.\n\n```python\nlist(range(5))       # [0,1,2,3,4]\nlist("abc")          # ["a","b","c"]\nlist({1,2,3})        # [1,2,3]  (order not guaranteed)\nlist(d.items())      # list of (key,value) tuples\n```',
            params: [p('iterable: Iterable = ()', '**iterable** *(default: `()`)*\n\nAny iterable. Omit to create an empty list.')],
        }],
        dict: [
            {
                label: 'dict(**kwargs) -> dict',
                doc: '**dict** `-> dict`\n\nCreate a dictionary.\n\n```python\ndict(a=1, b=2)            # {"a":1,"b":2}\ndict(zip(keys, values))   # from two sequences\ndict(existing_dict)       # shallow copy\n```',
                params: [p('**kwargs', '**kwargs**\n\nKeyword arguments become key-value pairs.')],
            },
            {
                label: 'dict(mapping: Mapping) -> dict',
                doc: '**dict(mapping)** — Create dict from a mapping or iterable of key-value pairs.',
                params: [p('mapping: Mapping', '**mapping** `Mapping`\n\nExisting mapping or iterable of `(key, value)` pairs.')],
            },
        ],
        set: [{
            label: 'set(iterable: Iterable = ()) -> set',
            doc: '**set** `-> set`\n\nCreate a mutable unordered collection with no duplicates.\n\n```python\nset([1,2,2,3])   # {1,2,3}\nset("hello")     # {"h","e","l","o"}\nset()            # empty set (not {}!)\n```',
            params: [p('iterable: Iterable = ()', '**iterable** *(default: `()`)*\n\nDuplicates are automatically removed.')],
        }],
        tuple: [{
            label: 'tuple(iterable: Iterable = ()) -> tuple',
            doc: '**tuple** `-> tuple`\n\nCreate an immutable sequence from an iterable.\n\n```python\ntuple([1,2,3])   # (1,2,3)\ntuple("abc")     # ("a","b","c")\ntuple()          # ()\n```',
            params: [p('iterable: Iterable = ()', '**iterable** *(default: `()`)*\n\nAny iterable to convert to a tuple.')],
        }],
        open: [{
            label: 'open(file: str | Path, mode: str = "r", encoding: str = None, errors: str = None) -> IO',
            doc: '**open** `-> IO`\n\nOpen a file and return a file object.\n\n```python\nwith open("data.txt", "r", encoding="utf-8") as f:\n    text = f.read()\nwith open("out.bin", "wb") as f:\n    f.write(bytes_data)\n```\n\n**mode** values:\n- `"r"` read text *(default)*\n- `"w"` write text (truncates)\n- `"a"` append text\n- `"rb"` / `"wb"` binary read/write\n- `"x"` create, fail if exists',
            params: [
                p('file: str | Path',       '**file** `str | Path`\n\nPath to the file to open.'),
                p('mode: str = "r"',        '**mode** `str` *(default: `"r"`)*\n\n`"r"` read, `"w"` write, `"a"` append, `"b"` binary, `"x"` exclusive create.'),
                p('encoding: str = None',   '**encoding** `str` *(optional)*\n\nText encoding, e.g. `"utf-8"`. Defaults to locale encoding.'),
                p('errors: str = None',     '**errors** `str` *(optional)*\n\nError handling: `"strict"` (default), `"ignore"`, `"replace"`.'),
            ],
        }],
        isinstance: [{
            label: 'isinstance(object: object, classinfo: type | tuple[type, ...]) -> bool',
            doc: '**isinstance** `-> bool`\n\nReturn `True` if `object` is an instance of `classinfo` (or any of a tuple of types).\n\n```python\nisinstance(42, int)           # True\nisinstance(42, (int, float))  # True  (tuple of types)\nisinstance("hi", str)         # True\n```',
            params: [
                p('object: object',                      '**object** `object`\n\nThe object to test.'),
                p('classinfo: type | tuple[type, ...]', '**classinfo** `type | tuple`\n\nA type or tuple of types. Returns `True` if object matches any.'),
            ],
        }],
        issubclass: [{ label: 'issubclass(cls: type, classinfo: type | tuple) -> bool', doc: '**issubclass** `-> bool`\n\nReturn `True` if `cls` is a subclass of `classinfo`.', params: [p('cls: type','**cls** `type`\n\nThe class to test.'),p('classinfo: type | tuple','**classinfo** `type | tuple`\n\nA type or tuple of types.')] }],
        hasattr:    [{ label: 'hasattr(object: object, name: str) -> bool', doc: '**hasattr** `-> bool`\n\nReturn `True` if `object` has an attribute named `name`.\n\n```python\nhasattr(obj, "x")   # True if obj.x exists\n```', params: [p('object: object','**object**\n\nThe object to inspect.'),p('name: str','**name** `str`\n\nAttribute name to look up.')] }],
        getattr:    [{ label: 'getattr(object: object, name: str, default=...) -> Any', doc: '**getattr** `-> Any`\n\nGet the value of the named attribute.\n\n```python\ngetattr(obj, "x")          # obj.x\ngetattr(obj, "x", None)    # None if missing\n```', params: [p('object: object','**object**\n\nThe object to read from.'),p('name: str','**name** `str`\n\nAttribute name.'),p('default = ...','**default** *(optional)*\n\nReturn this if attribute not found. Omit to raise `AttributeError`.')] }],
        setattr:    [{ label: 'setattr(object: object, name: str, value: Any) -> None', doc: '**setattr** `-> None`\n\nSet the named attribute to `value`.\n\n```python\nsetattr(obj, "x", 42)  # same as obj.x = 42\n```', params: [p('object: object','**object**\n\nTarget object.'),p('name: str','**name** `str`\n\nAttribute name.'),p('value: Any','**value**\n\nValue to assign.')] }],
        delattr:    [{ label: 'delattr(object: object, name: str) -> None', doc: '**delattr** `-> None`\n\nDelete the named attribute from `object`.', params: [p('object: object','**object**\n\nTarget object.'),p('name: str','**name** `str`\n\nAttribute to delete.')] }],
        type:       [{ label: 'type(object: object) -> type', doc: '**type** `-> type`\n\nReturn the type of an object.\n\n```python\ntype(42)      # <class "int">\ntype("hi")    # <class "str">\ntype(x) is int  # preferred identity check\n```', params: [p('object: object','**object**\n\nThe object whose type to return.')] }],
        callable:   [{ label: 'callable(object: object) -> bool', doc: '**callable** `-> bool`\n\nReturn `True` if `object` has a `__call__` method (appears callable).', params: [p('object: object','**object**\n\nThe object to check.')] }],
        repr:       [{ label: 'repr(object: object) -> str', doc: '**repr** `-> str`\n\nReturn a developer-friendly string representation.\n\n```python\nrepr([1,2,3])  # "[1, 2, 3]"\nrepr("hi")     # "\'hi\'"\n```', params: [p('object: object','**object**\n\nConverted using `object.__repr__()`.')] }],
        id:         [{ label: 'id(object: object) -> int', doc: '**id** `-> int`\n\nReturn the memory address (identity) of object. Guaranteed unique while the object exists.', params: [p('object: object','**object**\n\nAny Python object.')] }],
        hash:       [{ label: 'hash(object: object) -> int', doc: '**hash** `-> int`\n\nReturn the hash value. Objects equal under `==` have the same hash.', params: [p('object: object','**object**\n\nMust be hashable (immutable). Lists/dicts raise `TypeError`.')] }],
        dir:        [{ label: 'dir(object: object = None) -> list[str]', doc: '**dir** `-> list[str]`\n\nReturn a list of names in the current scope, or attributes of `object`.\n\n```python\ndir([])        # all list methods\ndir()          # local variable names\n```', params: [p('object: object = None','**object** *(optional)*\n\nOmit for local scope; pass an object to see its attributes.')] }],
        vars:       [{ label: 'vars(object: object = None) -> dict', doc: '**vars** `-> dict`\n\nReturn the `__dict__` of `object`. Without argument, returns `locals()`.', params: [p('object: object = None','**object** *(optional)*\n\nMust have a `__dict__`. Omit for current scope.')] }],
        input:      [{ label: 'input(prompt: str = "") -> str', doc: '**input** `-> str`\n\nRead a line from standard input, stripping the trailing newline.\n\n```python\nname = input("Name: ")      # blocks until Enter pressed\nage  = int(input("Age: "))\n```', params: [p('prompt: str = ""','**prompt** `str` *(default: `""`)*\n\nText printed before waiting for input.')] }],
        format:     [{ label: 'format(value: Any, format_spec: str = "") -> str', doc: '**format** `-> str`\n\nFormat `value` using `format_spec`. Calls `value.__format__(format_spec)`.\n\n```python\nformat(3.14159, ".2f")  # "3.14"\nformat(255, "#010x")    # "0x000000ff"\nformat(42, "08b")       # "00101010"\n```', params: [p('value: Any','**value**\n\nThe value to format.'),p('format_spec: str = ""','**format_spec** `str` *(default: `""`)*\n\nMini-language spec: `[fill][align][sign][#][0][width][.prec][type]`')] }],
        eval:       [{ label: 'eval(expression: str, globals: dict = None, locals: dict = None) -> Any', doc: '**eval** `-> Any`\n\nEvaluate a Python expression string and return its value.\n\n```python\neval("2 + 2")          # 4\neval("x * 2", {"x":5}) # 10\n```\n\n⚠️ Never eval untrusted input.', params: [p('expression: str','**expression** `str`\n\nA Python expression string.'),p('globals: dict = None','**globals** *(optional)*\n\nGlobal namespace dict.'),p('locals: dict = None','**locals** *(optional)*\n\nLocal namespace dict.')] }],
        exec:       [{ label: 'exec(object: str | code, globals: dict = None, locals: dict = None) -> None', doc: '**exec** `-> None`\n\nExecute a Python statement or code object.\n\n⚠️ Never exec untrusted input.', params: [p('object: str | code','**object**\n\nA Python statement string or compiled code object.'),p('globals: dict = None','**globals** *(optional)*.'),p('locals: dict = None','**locals** *(optional)*.')] }],
        compile:    [{ label: 'compile(source: str, filename: str, mode: str, flags: int = 0) -> code', doc: '**compile** `-> code`\n\nCompile source into a code object.', params: [p('source: str','**source** `str`\n\nPython source code.'),p('filename: str','**filename** `str`\n\nFilename for error messages (use `"<string>"` for dynamic code).'),p('mode: str','**mode** `str`\n\n`"exec"` for statements, `"eval"` for expressions, `"single"` for REPL.'),p('flags: int = 0','**flags** `int` *(optional)*\n\nCompiler flags.')] }],
        pow:        [
            { label: 'pow(base: N, exp: N) -> N', doc: '**pow** `-> N`\n\nRaise `base` to the power `exp`. Equivalent to `base ** exp`.\n\n```python\npow(2, 10)      # 1024\npow(2.0, 0.5)   # 1.4142...\n```', params: [p('base: N','**base** `N`\n\nThe base number.'),p('exp: N','**exp** `N`\n\nThe exponent.')] },
            { label: 'pow(base: int, exp: int, mod: int) -> int', doc: '**pow(base, exp, mod)** `-> int`\n\nFast modular exponentiation: `(base ** exp) % mod`. More efficient than `pow(b,e) % m` for large numbers.', params: [p('base: int','**base** `int`\n\nBase integer.'),p('exp: int','**exp** `int`\n\nExponent (must be non-negative).'),p('mod: int','**mod** `int`\n\nModulus.')] },
        ],
        divmod:     [{ label: 'divmod(a: N, b: N) -> tuple[N, N]', doc: '**divmod** `-> tuple[N, N]`\n\nReturn `(a // b, a % b)` as a tuple in a single operation.\n\n```python\ndivmod(17, 5)    # (3, 2)  → 17 = 3*5 + 2\ndivmod(-7, 3)    # (-3, 2)\n```', params: [p('a: N','**a** `N`\n\nDividend.'),p('b: N','**b** `N`\n\nDivisor.')] }],
        complex:    [{ label: 'complex(real: float = 0, imag: float = 0) -> complex', doc: '**complex** `-> complex`\n\nCreate a complex number `real + imag*j`.\n\n```python\ncomplex(3, 4)    # (3+4j)\nabs(complex(3,4)) # 5.0\n```', params: [p('real: float = 0','**real** `float` *(default: `0`)*\n\nThe real part.'),p('imag: float = 0','**imag** `float` *(default: `0`)*\n\nThe imaginary part.')] }],
        bool:       [{ label: 'bool(x: object = False) -> bool', doc: '**bool** `-> bool`\n\nConvert to `True` or `False` using truthiness rules.\n\n```python\nbool(0)    # False\nbool("")   # False\nbool([])   # False\nbool(1)    # True\nbool("hi") # True\n```', params: [p('x: object = False','**x** *(default: `False`)*\n\nAny object. Falsy: `0`, `""`, `[]`, `{}`, `None`, `False`.')] }],
        bin:        [{ label: 'bin(x: int) -> str', doc: '**bin** `-> str`\n\nReturn binary string prefixed with `"0b"`.\n\n```python\nbin(10)   # "0b1010"\nbin(-10)  # "-0b1010"\n```', params: [p('x: int','**x** `int`\n\nInteger to convert.')] }],
        oct:        [{ label: 'oct(x: int) -> str', doc: '**oct** `-> str`\n\nReturn octal string prefixed with `"0o"`.\n\n```python\noct(8)   # "0o10"\noct(255) # "0o377"\n```', params: [p('x: int','**x** `int`\n\nInteger to convert.')] }],
        hex:        [{ label: 'hex(x: int) -> str', doc: '**hex** `-> str`\n\nReturn lowercase hexadecimal string prefixed with `"0x"`.\n\n```python\nhex(255)   # "0xff"\nhex(256)   # "0x100"\n```', params: [p('x: int','**x** `int`\n\nInteger to convert.')] }],
        chr:        [{ label: 'chr(i: int) -> str', doc: '**chr** `-> str`\n\nReturn the single-character string for Unicode code point `i`.\n\n```python\nchr(65)     # "A"\nchr(0x1F600) # "😀"\n```', params: [p('i: int','**i** `int`\n\nUnicode code point in range 0–1,114,111.')] }],
        ord:        [{ label: 'ord(c: str) -> int', doc: '**ord** `-> int`\n\nReturn the Unicode code point of a single character.\n\n```python\nord("A")  # 65\nord("€")  # 8364\n```', params: [p('c: str','**c** `str`\n\nA string of exactly one character.')] }],
        iter:       [
            { label: 'iter(iterable: Iterable) -> Iterator', doc: '**iter** `-> Iterator`\n\nReturn an iterator for the given iterable.', params: [p('iterable: Iterable','**iterable**\n\nAny object implementing `__iter__`.')] },
            { label: 'iter(callable: Callable, sentinel: Any) -> Iterator', doc: '**iter(callable, sentinel)** `-> Iterator`\n\nCall `callable` repeatedly until it returns `sentinel`.\n\n```python\nfor block in iter(lambda: f.read(4096), b""):\n    process(block)\n```', params: [p('callable: Callable','**callable**\n\nZero-argument callable called on each iteration.'),p('sentinel: Any','**sentinel**\n\nIteration stops when this value is returned.')] },
        ],
        next:       [{ label: 'next(iterator: Iterator, default: Any = ...) -> Any', doc: '**next** `-> Any`\n\nReturn the next item from the iterator.\n\n```python\nit = iter([1,2,3])\nnext(it)           # 1\nnext(it, "done")   # 2  (default only used at end)\n```', params: [p('iterator: Iterator','**iterator** `Iterator`\n\nAn iterator object (returned by `iter()` or a generator).'),p('default: Any = ...','**default** *(optional)*\n\nReturn this when the iterator is exhausted. Omit to raise `StopIteration`.')] }],
        reversed:   [{ label: 'reversed(sequence: Sequence) -> Iterator', doc: '**reversed** `-> Iterator`\n\nReturn a reverse iterator over the sequence.\n\n```python\nlist(reversed([1,2,3]))  # [3,2,1]\nfor x in reversed(range(10)): ...\n```', params: [p('sequence: Sequence','**sequence** `Sequence`\n\nMust have `__reversed__` or `__len__` and `__getitem__`.')] }],
        slice:      [
            { label: 'slice(stop: int) -> slice', doc: '**slice(stop)** — Equivalent to `[0:stop]`.', params: [p('stop: int','**stop** `int`\n\nEnd of the slice (exclusive).')] },
            { label: 'slice(start: int, stop: int, step: int = None) -> slice', doc: '**slice(start, stop, step)** — Equivalent to `[start:stop:step]`.\n\n```python\ns = slice(1, 10, 2)\nmy_list[s]   # same as my_list[1:10:2]\n```', params: [p('start: int','**start** `int`\n\nStart of the slice.'),p('stop: int','**stop** `int`\n\nEnd of the slice (exclusive).'),p('step: int = None','**step** `int` *(optional)*\n\nStep size. `None` means 1.')] },
        ],
        any:        [{ label: 'any(iterable: Iterable) -> bool', doc: '**any** `-> bool`\n\nReturn `True` if **any** element is truthy. Short-circuits on first truthy value.\n\n```python\nany([0, 0, 1])        # True\nany(x > 0 for x in lst)\n```', params: [p('iterable: Iterable','**iterable**\n\nAny iterable of values.')] }],
        all:        [{ label: 'all(iterable: Iterable) -> bool', doc: '**all** `-> bool`\n\nReturn `True` if **all** elements are truthy. Short-circuits on first falsy value.\n\n```python\nall([1, 2, 3])         # True\nall(x > 0 for x in lst)\n```', params: [p('iterable: Iterable','**iterable**\n\nAny iterable of values.')] }],
        bytes:      [
            { label: 'bytes(source: int | Iterable[int] = b"") -> bytes', doc: '**bytes** `-> bytes`\n\nCreate an immutable bytes object.', params: [p('source: int | Iterable[int] = b""','**source**\n\nInteger length (zeros), iterable of 0–255 ints, or omit for empty.')] },
            { label: 'bytes(source: str, encoding: str, errors: str = "strict") -> bytes', doc: '**bytes(str, encoding)** — Encode a string to bytes.', params: [p('source: str','**source** `str`\n\nString to encode.'),p('encoding: str','**encoding** `str`\n\nEncoding name, e.g. `"utf-8"`.'),p('errors: str = "strict"','**errors** *(default: `"strict"`)*\n\n`"strict"`, `"ignore"`, or `"replace"`.')] },
        ],
        bytearray:  [{ label: 'bytearray(source: int | Iterable[int] = b"") -> bytearray', doc: '**bytearray** `-> bytearray`\n\nMutable sequence of bytes. Same constructor as `bytes()`.', params: [p('source: int | Iterable[int] = b""','**source**\n\nLength (zero-filled), iterable of 0–255 ints, or empty.')] }],
        memoryview: [{ label: 'memoryview(object: bytes | bytearray) -> memoryview', doc: '**memoryview** `-> memoryview`\n\nExpose a bytes-like object\'s internal buffer without copying.', params: [p('object: bytes | bytearray','**object**\n\nA bytes-like object (bytes, bytearray, array.array, etc.).')] }],
        frozenset:  [{ label: 'frozenset(iterable: Iterable = ()) -> frozenset', doc: '**frozenset** `-> frozenset`\n\nImmutable set. Can be used as a dict key or set element.', params: [p('iterable: Iterable = ()','**iterable** *(default: `()`)*\n\nDuplicates removed; order not preserved.')] }],
        super:      [
            { label: 'super() -> super', doc: '**super()** — Zero-argument form inside a method. Returns proxy to the parent class.\n\n```python\nclass Child(Parent):\n    def __init__(self):\n        super().__init__()\n```', params: [] },
            { label: 'super(type: type, object_or_type: object) -> super', doc: '**super(type, object)** — Explicit form.', params: [p('type: type','**type**\n\nThe class to skip.'),p('object_or_type: object','**object_or_type**\n\nThe instance or class to bind to.')] },
        ],
        property:   [{ label: 'property(fget: Callable = None, fset: Callable = None, fdel: Callable = None, doc: str = None) -> property', doc: '**property** — Create a managed attribute descriptor.\n\n```python\nclass C:\n    @property\n    def x(self): return self._x\n    @x.setter\n    def x(self, v): self._x = v\n```', params: [p('fget: Callable = None','**fget** *(optional)*\n\nGetter function.'),p('fset: Callable = None','**fset** *(optional)*\n\nSetter function.'),p('fdel: Callable = None','**fdel** *(optional)*\n\nDeleter function.'),p('doc: str = None','**doc** *(optional)*\n\nDocstring.')] }],
        staticmethod:[{ label: 'staticmethod(function: Callable) -> staticmethod', doc: '**staticmethod** — Declare a static method. No implicit `self` or `cls` argument.\n\n```python\nclass C:\n    @staticmethod\n    def helper(x): return x * 2\n```', params: [p('function: Callable','**function**\n\nThe function to wrap.')] }],
        classmethod:[{ label: 'classmethod(function: Callable) -> classmethod', doc: '**classmethod** — Declare a class method. Receives `cls` as the first argument.\n\n```python\nclass C:\n    @classmethod\n    def create(cls): return cls()\n```', params: [p('function: Callable','**function**\n\nThe function to wrap. First arg will be the class.')] }],
        // ─ String methods
        join:       [{ label: 'str.join(iterable: Iterable[str]) -> str', doc: '**str.join** `-> str`\n\nJoin an iterable of strings, inserting this string as separator.\n\n```python\n", ".join(["a","b","c"])   # "a, b, c"\n"\\n".join(lines)           # newline-separated\n"".join(chars)             # concatenate\n```', params: [p('iterable: Iterable[str]','**iterable** `Iterable[str]`\n\nAll elements must be strings.')] }],
        split:      [{ label: 'str.split(sep: str = None, maxsplit: int = -1) -> list[str]', doc: '**str.split** `-> list[str]`\n\nSplit string by separator.\n\n```python\n"a,b,c".split(",")          # ["a","b","c"]\n"  a  b  ".split()          # ["a","b"]  (whitespace)\n"a:b:c".split(":", 1)       # ["a","b:c"]\n```', params: [p('sep: str = None','**sep** `str` *(default: `None`)*\n\nSeparator string. `None` splits on any whitespace and strips edges.'),p('maxsplit: int = -1','**maxsplit** `int` *(default: `-1`)*\n\nMaximum number of splits. `-1` means unlimited.')] }],
        rsplit:     [{ label: 'str.rsplit(sep: str = None, maxsplit: int = -1) -> list[str]', doc: '**str.rsplit** `-> list[str]`\n\nLike `split()` but splits from the right.\n\n```python\n"a:b:c".rsplit(":", 1)   # ["a:b","c"]\n```', params: [p('sep: str = None','**sep** `str` *(optional)*.'),p('maxsplit: int = -1','**maxsplit** `int` *(default: `-1`)* — Max splits from the right.')] }],
        splitlines: [{ label: 'str.splitlines(keepends: bool = False) -> list[str]', doc: '**str.splitlines** `-> list[str]`\n\nSplit at line boundaries (`\\n`, `\\r\\n`, etc.).\n\n```python\n"a\\nb\\nc".splitlines()        # ["a","b","c"]\n"a\\nb".splitlines(True)       # ["a\\n","b"]\n```', params: [p('keepends: bool = False','**keepends** `bool` *(default: `False`)*\n\nIf `True`, line endings are included in the result.')] }],
        strip:      [{ label: 'str.strip(chars: str = None) -> str', doc: '**str.strip** `-> str`\n\nRemove leading and trailing characters.\n\n```python\n"  hello  ".strip()      # "hello"\n"xxhelloxx".strip("x")   # "hello"\n```', params: [p('chars: str = None','**chars** `str` *(optional)*\n\nCharacters to remove. Omit to strip whitespace.')] }],
        lstrip:     [{ label: 'str.lstrip(chars: str = None) -> str', doc: '**str.lstrip** `-> str`\n\nRemove leading (left) characters only.', params: [p('chars: str = None','**chars** *(optional)* — Characters to remove. Omit for whitespace.')] }],
        rstrip:     [{ label: 'str.rstrip(chars: str = None) -> str', doc: '**str.rstrip** `-> str`\n\nRemove trailing (right) characters only.', params: [p('chars: str = None','**chars** *(optional)* — Characters to remove. Omit for whitespace.')] }],
        replace:    [{ label: 'str.replace(old: str, new: str, count: int = -1) -> str', doc: '**str.replace** `-> str`\n\nReturn a copy with occurrences of `old` replaced by `new`.\n\n```python\n"aabbcc".replace("b","X")      # "aaXXcc"\n"aabbcc".replace("b","X", 1)   # "aaXbcc"\n```', params: [p('old: str','**old** `str`\n\nSubstring to find.'),p('new: str','**new** `str`\n\nReplacement substring.'),p('count: int = -1','**count** `int` *(default: `-1`)*\n\nMax replacements. `-1` replaces all.')] }],
        find:       [{ label: 'str.find(sub: str, start: int = 0, end: int = None) -> int', doc: '**str.find** `-> int`\n\nReturn the lowest index where `sub` is found, or `-1`.\n\n```python\n"hello".find("l")      # 2\n"hello".find("l", 3)   # 3\n"hello".find("x")      # -1\n```', params: [p('sub: str','**sub** `str`\n\nSubstring to search for.'),p('start: int = 0','**start** `int` *(optional)* — Search from this index.'),p('end: int = None','**end** `int` *(optional)* — Stop before this index.')] }],
        rfind:      [{ label: 'str.rfind(sub: str, start: int = 0, end: int = None) -> int', doc: '**str.rfind** `-> int`\n\nLike `find()` but returns the highest (rightmost) index.', params: [p('sub: str','**sub** `str`\n\nSubstring to search for.'),p('start: int = 0','**start** *(optional)*.'),p('end: int = None','**end** *(optional)*.')] }],
        index:      [{ label: 'str.index(sub: str, start: int = 0, end: int = None) -> int', doc: '**str.index** `-> int`\n\nLike `find()` but raises `ValueError` instead of returning `-1`.', params: [p('sub: str','**sub** `str`\n\nSubstring to search for.'),p('start: int = 0','**start** *(optional)*.'),p('end: int = None','**end** *(optional)*.')] }],
        rindex:     [{ label: 'str.rindex(sub: str, start: int = 0, end: int = None) -> int', doc: '**str.rindex** `-> int`\n\nLike `rfind()` but raises `ValueError` instead of returning `-1`.', params: [p('sub: str','**sub** `str`\n\nSubstring to search for.'),p('start: int = 0','**start** *(optional)*.'),p('end: int = None','**end** *(optional)*.')] }],
        count:      [{ label: 'str.count(sub: str, start: int = 0, end: int = None) -> int', doc: '**str.count** `-> int`\n\nCount non-overlapping occurrences of `sub`.\n\n```python\n"banana".count("a")    # 3\n"banana".count("an")   # 2\n```', params: [p('sub: str','**sub** `str`\n\nSubstring to count.'),p('start: int = 0','**start** *(optional)*.'),p('end: int = None','**end** *(optional)*.')] }],
        startswith: [{ label: 'str.startswith(prefix: str | tuple[str], start: int = 0, end: int = None) -> bool', doc: '**str.startswith** `-> bool`\n\n```python\n"hello".startswith("he")         # True\n"hello".startswith(("he","Ho"))  # True (tuple of prefixes)\n```', params: [p('prefix: str | tuple[str]','**prefix** `str | tuple[str]`\n\nPrefix or tuple of prefixes to test.'),p('start: int = 0','**start** *(optional)* — Test from this index.'),p('end: int = None','**end** *(optional)* — Test before this index.')] }],
        endswith:   [{ label: 'str.endswith(suffix: str | tuple[str], start: int = 0, end: int = None) -> bool', doc: '**str.endswith** `-> bool`\n\nTest whether the string ends with `suffix`.', params: [p('suffix: str | tuple[str]','**suffix** `str | tuple[str]`\n\nSuffix or tuple of suffixes.'),p('start: int = 0','**start** *(optional)*.'),p('end: int = None','**end** *(optional)*.')] }],
        encode:     [{ label: 'str.encode(encoding: str = "utf-8", errors: str = "strict") -> bytes', doc: '**str.encode** `-> bytes`\n\nEncode the string to bytes.\n\n```python\n"hello".encode()           # b"hello"\n"café".encode("utf-8")     # b"caf\\xc3\\xa9"\n```', params: [p('encoding: str = "utf-8"','**encoding** `str` *(default: `"utf-8"`)*\n\nTarget encoding.'),p('errors: str = "strict"','**errors** *(default: `"strict"`)*\n\n`"strict"`, `"ignore"`, `"replace"`, `"xmlcharrefreplace"`.')] }],
        zfill:      [{ label: 'str.zfill(width: int) -> str', doc: '**str.zfill** `-> str`\n\nPad with zeros on the left to fill `width`. Preserves sign.\n\n```python\n"42".zfill(5)    # "00042"\n"-3".zfill(5)    # "-0003"\n```', params: [p('width: int','**width** `int`\n\nMinimum total width of the result.')] }],
        center:     [{ label: 'str.center(width: int, fillchar: str = " ") -> str', doc: '**str.center** `-> str`\n\nCenter string in a field of `width`, padded with `fillchar`.', params: [p('width: int','**width** `int`\n\nTotal field width.'),p('fillchar: str = " "','**fillchar** `str` *(default: `" "`)*\n\nSingle fill character.')] }],
        ljust:      [{ label: 'str.ljust(width: int, fillchar: str = " ") -> str', doc: '**str.ljust** `-> str`\n\nLeft-justify string in a field of `width`.', params: [p('width: int','**width** `int`\n\nTotal field width.'),p('fillchar: str = " "','**fillchar** *(default: `" "`)*.')] }],
        rjust:      [{ label: 'str.rjust(width: int, fillchar: str = " ") -> str', doc: '**str.rjust** `-> str`\n\nRight-justify string in a field of `width`.', params: [p('width: int','**width** `int`\n\nTotal field width.'),p('fillchar: str = " "','**fillchar** *(default: `" "`)*.')] }],
        // ─ List methods
        append:     [{ label: 'list.append(item: Any) -> None', doc: '**list.append** `-> None`\n\nAdd `item` to the end of the list.\n\n```python\nlst = [1,2]\nlst.append(3)   # [1,2,3]\n```', params: [p('item: Any','**item**\n\nThe object to add.')] }],
        extend:     [{ label: 'list.extend(iterable: Iterable) -> None', doc: '**list.extend** `-> None`\n\nAppend all items from `iterable`. Modifies in place.\n\n```python\nlst = [1,2]\nlst.extend([3,4])  # [1,2,3,4]\nlst.extend("ab")   # [1,2,3,4,"a","b"]\n```', params: [p('iterable: Iterable','**iterable**\n\nAny iterable to append from.')] }],
        insert:     [{ label: 'list.insert(index: int, item: Any) -> None', doc: '**list.insert** `-> None`\n\nInsert `item` before position `index`.\n\n```python\nlst = [1,3]\nlst.insert(1, 2)   # [1,2,3]\nlst.insert(0, 0)   # insert at start\n```', params: [p('index: int','**index** `int`\n\nPosition to insert before.'),p('item: Any','**item**\n\nObject to insert.')] }],
        remove:     [{ label: 'list.remove(item: Any) -> None', doc: '**list.remove** `-> None`\n\nRemove the **first** occurrence of `item`. Raises `ValueError` if not found.\n\n```python\nlst = [1,2,3,2]\nlst.remove(2)   # [1,3,2]  (only first)\n```', params: [p('item: Any','**item**\n\nThe value to remove.')] }],
        pop:        [{ label: 'list.pop(index: int = -1) -> Any', doc: '**list.pop** `-> Any`\n\nRemove and return item at `index` (default last).\n\n```python\nlst = [1,2,3]\nlst.pop()     # 3  →  [1,2]\nlst.pop(0)    # 1  →  [2]\n```', params: [p('index: int = -1','**index** `int` *(default: `-1`)*\n\nIndex to remove. `-1` removes the last item.')] }],
        sort:       [{ label: 'list.sort(*, key: Callable = None, reverse: bool = False) -> None', doc: '**list.sort** `-> None`\n\nSort the list **in place**. Use `sorted()` to return a new list.\n\n```python\nlst.sort()                          # ascending\nlst.sort(reverse=True)              # descending\nlst.sort(key=lambda x: x["name"])  # by key\n```', params: [p('key: Callable = None','**key** `Callable` *(optional)*\n\nOne-argument key function for comparison.'),p('reverse: bool = False','**reverse** `bool` *(default: `False`)*\n\nIf `True`, sort in descending order.')] }],
        // ─ Dict methods
        get:        [{ label: 'dict.get(key: K, default: V = None) -> V | None', doc: '**dict.get** `-> V | None`\n\nReturn the value for `key`, or `default` if absent (no `KeyError`).\n\n```python\nd = {"a":1}\nd.get("a")      # 1\nd.get("b")      # None\nd.get("b", 0)   # 0\n```', params: [p('key: K','**key**\n\nThe dictionary key to look up.'),p('default: V = None','**default** *(default: `None`)*\n\nReturned when key is not found.')] }],
        update:     [{ label: 'dict.update(other: dict | Iterable = {}, **kwargs) -> None', doc: '**dict.update** `-> None`\n\nUpdate dict with key/value pairs from `other` and/or keyword args.\n\n```python\nd.update({"b":2})          # from dict\nd.update([("c",3)])        # from iterable\nd.update(d=4)              # from kwargs\n```', params: [p('other: dict | Iterable = {}','**other** *(optional)*\n\nA dict or iterable of key-value pairs.'),p('**kwargs','**kwargs**\n\nKeyword arguments become key-value pairs.')] }],
        setdefault: [{ label: 'dict.setdefault(key: K, default: V = None) -> V', doc: '**dict.setdefault** `-> V`\n\nReturn value for `key`. If key absent, insert `key: default` and return `default`.\n\n```python\nd = {}\nd.setdefault("x", []).append(1)  # d = {"x":[1]}\n```', params: [p('key: K','**key**\n\nKey to look up or insert.'),p('default: V = None','**default** *(default: `None`)*\n\nValue to insert and return if key is absent.')] }],
        // ─ math module
        sin:        [{ label: 'math.sin(x: float) -> float', doc: '**math.sin** `-> float`\n\nReturn the sine of `x` radians.\n\n```python\nmath.sin(math.pi / 2)  # 1.0\nmath.sin(0)            # 0.0\n```', params: [p('x: float','**x** `float`\n\nAngle in **radians**. Use `math.radians(degrees)` to convert.')] }],
        cos:        [{ label: 'math.cos(x: float) -> float', doc: '**math.cos** `-> float`\n\nReturn the cosine of `x` radians.\n\n```python\nmath.cos(0)         # 1.0\nmath.cos(math.pi)   # -1.0\n```', params: [p('x: float','**x** `float`\n\nAngle in **radians**.')] }],
        tan:        [{ label: 'math.tan(x: float) -> float', doc: '**math.tan** `-> float`\n\nReturn the tangent of `x` radians.', params: [p('x: float','**x** `float`\n\nAngle in **radians**.')] }],
        asin:       [{ label: 'math.asin(x: float) -> float', doc: '**math.asin** `-> float`\n\nReturn the arc sine of `x` in radians. Domain: `[-1, 1]`.', params: [p('x: float','**x** `float`\n\nValue in `[-1, 1]`.')] }],
        acos:       [{ label: 'math.acos(x: float) -> float', doc: '**math.acos** `-> float`\n\nReturn the arc cosine of `x` in radians. Domain: `[-1, 1]`.', params: [p('x: float','**x** `float`\n\nValue in `[-1, 1]`.')] }],
        atan:       [{ label: 'math.atan(x: float) -> float', doc: '**math.atan** `-> float`\n\nReturn the arc tangent of `x` in radians. Result in `(-π/2, π/2)`.', params: [p('x: float','**x** `float`\n\nAny real number.')] }],
        atan2:      [{ label: 'math.atan2(y: float, x: float) -> float', doc: '**math.atan2** `-> float`\n\nReturn `atan(y/x)` in radians, choosing the correct quadrant.\n\n```python\nmath.atan2(1, 1)   # π/4  (45°)\nmath.atan2(1, -1)  # 3π/4 (135°)\n```', params: [p('y: float','**y** `float`\n\nY coordinate (numerator).'),p('x: float','**x** `float`\n\nX coordinate (denominator).')] }],
        sqrt:       [{ label: 'math.sqrt(x: float) -> float', doc: '**math.sqrt** `-> float`\n\nReturn the square root of `x`.\n\n```python\nmath.sqrt(9)    # 3.0\nmath.sqrt(2)    # 1.4142...\n```', params: [p('x: float','**x** `float`\n\nNon-negative number.')] }],
        exp:        [{ label: 'math.exp(x: float) -> float', doc: '**math.exp** `-> float`\n\nReturn `e ** x` (more accurate than `math.e ** x` for small `x`).\n\n```python\nmath.exp(0)  # 1.0\nmath.exp(1)  # 2.71828...\n```', params: [p('x: float','**x** `float`\n\nThe exponent.')] }],
        log:        [
            { label: 'math.log(x: float) -> float', doc: '**math.log(x)** `-> float`\n\nNatural logarithm (base *e*).', params: [p('x: float','**x** `float`\n\nPositive number.')] },
            { label: 'math.log(x: float, base: float) -> float', doc: '**math.log(x, base)** `-> float`\n\nLogarithm of `x` to the given `base`.\n\n```python\nmath.log(8, 2)   # 3.0  (log₂(8))\nmath.log(100,10) # 2.0\n```', params: [p('x: float','**x** `float`\n\nPositive number.'),p('base: float','**base** `float`\n\nLogarithm base.')] },
        ],
        log10:      [{ label: 'math.log10(x: float) -> float', doc: '**math.log10** `-> float`\n\nBase-10 logarithm. More accurate than `math.log(x, 10)`.\n\n```python\nmath.log10(1000)  # 3.0\n```', params: [p('x: float','**x** `float`\n\nPositive number.')] }],
        log2:       [{ label: 'math.log2(x: float) -> float', doc: '**math.log2** `-> float`\n\nBase-2 logarithm. More accurate than `math.log(x, 2)`.\n\n```python\nmath.log2(1024)  # 10.0\n```', params: [p('x: float','**x** `float`\n\nPositive number.')] }],
        floor:      [{ label: 'math.floor(x: float) -> int', doc: '**math.floor** `-> int`\n\nReturn the largest integer ≤ `x`.\n\n```python\nmath.floor(3.9)   # 3\nmath.floor(-3.1)  # -4\n```', params: [p('x: float','**x** `float`\n\nAny real number.')] }],
        ceil:       [{ label: 'math.ceil(x: float) -> int', doc: '**math.ceil** `-> int`\n\nReturn the smallest integer ≥ `x`.\n\n```python\nmath.ceil(3.1)   # 4\nmath.ceil(-3.9)  # -3\n```', params: [p('x: float','**x** `float`\n\nAny real number.')] }],
        radians:    [{ label: 'math.radians(x: float) -> float', doc: '**math.radians** `-> float`\n\nConvert degrees to radians.\n\n```python\nmath.radians(180)  # π ≈ 3.14159\nmath.radians(90)   # π/2 ≈ 1.5708\n```', params: [p('x: float','**x** `float`\n\nAngle in degrees.')] }],
        degrees:    [{ label: 'math.degrees(x: float) -> float', doc: '**math.degrees** `-> float`\n\nConvert radians to degrees.\n\n```python\nmath.degrees(math.pi)      # 180.0\nmath.degrees(math.pi / 2)  # 90.0\n```', params: [p('x: float','**x** `float`\n\nAngle in radians.')] }],
        hypot:      [{ label: 'math.hypot(*coordinates: float) -> float', doc: '**math.hypot** `-> float`\n\nEuclidean distance: `sqrt(x₁² + x₂² + …)`\n\n```python\nmath.hypot(3, 4)       # 5.0  (Pythagorean triple)\nmath.hypot(1, 1, 1)    # √3 ≈ 1.732\n```', params: [p('*coordinates: float','**coordinates** `float`\n\nCoordinate values (2D, 3D, or nD).')] }],
        gcd:        [{ label: 'math.gcd(*integers: int) -> int', doc: '**math.gcd** `-> int`\n\nGreatest common divisor.\n\n```python\nmath.gcd(12, 8)     # 4\nmath.gcd(12, 8, 6)  # 2\n```', params: [p('*integers: int','**integers** `int`\n\nTwo or more non-negative integers.')] }],
        factorial:  [{ label: 'math.factorial(n: int) -> int', doc: '**math.factorial** `-> int`\n\nReturn `n!` (n factorial).\n\n```python\nmath.factorial(5)   # 120  (5×4×3×2×1)\nmath.factorial(0)   # 1\n```', params: [p('n: int','**n** `int`\n\nNon-negative integer.')] }],
        comb:       [{ label: 'math.comb(n: int, k: int) -> int', doc: '**math.comb** `-> int`\n\nBinomial coefficient C(n, k) — ways to choose `k` items from `n` without repetition or order.\n\n```python\nmath.comb(5, 2)   # 10  (C(5,2))\n```', params: [p('n: int','**n** `int`\n\nTotal items.'),p('k: int','**k** `int`\n\nItems to choose.')] }],
        perm:       [{ label: 'math.perm(n: int, k: int = None) -> int', doc: '**math.perm** `-> int`\n\nOrdered ways to choose `k` items from `n`.\n\n```python\nmath.perm(5, 2)   # 20  (P(5,2))\nmath.perm(5)      # 120  (same as factorial)\n```', params: [p('n: int','**n** `int`\n\nTotal items.'),p('k: int = None','**k** `int` *(optional)*\n\nItems to arrange. Omit for `n!`.')] }],
        // ─ numpy
        array:      [{ label: 'np.array(object, dtype=None, copy=True) -> ndarray', doc: '**np.array** `-> ndarray`\n\nCreate an N-dimensional array.\n\n```python\nnp.array([1,2,3])           # 1-D\nnp.array([[1,2],[3,4]])     # 2-D matrix\nnp.array([0, 1, 0])         # Manim direction vector\n```', params: [p('object','**object**\n\nNested list, tuple, or array-like to convert.'),p('dtype = None','**dtype** *(optional)*\n\nData type e.g. `np.float64`, `np.int32`. Inferred if omitted.'),p('copy = True','**copy** `bool` *(default: `True`)*\n\nIf `False`, avoid copy if possible.')] }],
        zeros:      [{ label: 'np.zeros(shape: int | tuple, dtype: type = float) -> ndarray', doc: '**np.zeros** `-> ndarray`\n\nReturn an array filled with zeros.\n\n```python\nnp.zeros(3)        # [0. 0. 0.]\nnp.zeros((2,3))    # 2×3 matrix of zeros\n```', params: [p('shape: int | tuple','**shape** `int | tuple`\n\nDimensions e.g. `5` or `(3, 4)`.'),p('dtype: type = float','**dtype** *(default: `float`)*\n\nArray data type.')] }],
        ones:       [{ label: 'np.ones(shape: int | tuple, dtype: type = float) -> ndarray', doc: '**np.ones** `-> ndarray`\n\nReturn an array filled with ones.', params: [p('shape: int | tuple','**shape**\n\nDimensions.'),p('dtype: type = float','**dtype** *(default: `float`)*.')] }],
        linspace:   [{ label: 'np.linspace(start: float, stop: float, num: int = 50) -> ndarray', doc: '**np.linspace** `-> ndarray`\n\nReturn `num` evenly spaced values over `[start, stop]`.\n\n```python\nnp.linspace(0, 1, 5)   # [0, .25, .5, .75, 1]\nnp.linspace(0, TAU, 100)  # for Manim paths\n```', params: [p('start: float','**start** `float`\n\nFirst value.'),p('stop: float','**stop** `float`\n\nLast value (inclusive).'),p('num: int = 50','**num** `int` *(default: `50`)*\n\nNumber of samples.')] }],
        arange:     [{ label: 'np.arange(start: float, stop: float, step: float = 1) -> ndarray', doc: '**np.arange** `-> ndarray`\n\nReturn values in `[start, stop)` with spacing `step`.\n\n```python\nnp.arange(5)          # [0,1,2,3,4]\nnp.arange(0, 1, 0.1)  # [0.0, 0.1, ..., 0.9]\n```', params: [p('start: float','**start** `float`\n\nStart value.'),p('stop: float','**stop** `float`\n\nEnd value (exclusive).'),p('step: float = 1','**step** `float` *(default: `1`)*\n\nSpacing between values.')] }],
        dot:        [{ label: 'np.dot(a: ndarray, b: ndarray) -> ndarray | float', doc: '**np.dot** `-> ndarray | float`\n\nDot product of two arrays.\n\n```python\nnp.dot([1,2,3], [4,5,6])   # 32  (1*4+2*5+3*6)\n```', params: [p('a: ndarray','**a** `ndarray`\n\nFirst array.'),p('b: ndarray','**b** `ndarray`\n\nSecond array. Must be compatible shape.')] }],
        cross:      [{ label: 'np.cross(a: ndarray, b: ndarray) -> ndarray', doc: '**np.cross** `-> ndarray`\n\nCross product of two 3-D vectors.\n\n```python\nnp.cross([1,0,0], [0,1,0])  # [0,0,1]  (z-axis)\n```', params: [p('a: ndarray','**a** `ndarray`\n\nFirst 3-D vector.'),p('b: ndarray','**b** `ndarray`\n\nSecond 3-D vector.')] }],
        reshape:    [{ label: 'np.reshape(a: ndarray, newshape: int | tuple) -> ndarray', doc: '**np.reshape** `-> ndarray`\n\nReshape without changing data.\n\n```python\nnp.reshape(np.arange(6), (2,3))  # [[0,1,2],[3,4,5]]\nnp.reshape(a, -1)                 # flatten to 1-D\n```', params: [p('a: ndarray','**a** `ndarray`\n\nArray to reshape.'),p('newshape: int | tuple','**newshape** `int | tuple`\n\nNew shape. Use `-1` for auto-size on one axis.')] }],
        concatenate:[{ label: 'np.concatenate(arrays: sequence, axis: int = 0) -> ndarray', doc: '**np.concatenate** `-> ndarray`\n\nJoin arrays along an axis.\n\n```python\nnp.concatenate([[1,2],[3,4]])       # [1,2,3,4]\nnp.concatenate([a,b], axis=1)       # column-wise\n```', params: [p('arrays: sequence','**arrays** `sequence`\n\nSequence of arrays with compatible shapes.'),p('axis: int = 0','**axis** `int` *(default: `0`)*\n\nAxis along which to join.')] }],
        // ─ random module
        random:     [{ label: 'random.random() -> float', doc: '**random.random** `-> float`\n\nReturn a random float `N` such that `0.0 ≤ N < 1.0`.', params: [] }],
        randint:    [{ label: 'random.randint(a: int, b: int) -> int', doc: '**random.randint** `-> int`\n\nReturn a random integer `N` such that `a ≤ N ≤ b` (both endpoints included).', params: [p('a: int','**a** `int`\n\nLower bound (inclusive).'),p('b: int','**b** `int`\n\nUpper bound (inclusive).')] }],
        choice:     [{ label: 'random.choice(seq: Sequence) -> Any', doc: '**random.choice** `-> Any`\n\nReturn a random element from a non-empty sequence.', params: [p('seq: Sequence','**seq** `Sequence`\n\nNon-empty sequence to pick from.')] }],
        shuffle:    [{ label: 'random.shuffle(x: list) -> None', doc: '**random.shuffle** `-> None`\n\nShuffle the list `x` in place.', params: [p('x: list','**x** `list`\n\nList to shuffle in place.')] }],
        sample:     [{ label: 'random.sample(population: Sequence, k: int) -> list', doc: '**random.sample** `-> list`\n\nReturn `k` unique random elements from `population` (no replacement).', params: [p('population: Sequence','**population** `Sequence`\n\nSequence to sample from.'),p('k: int','**k** `int`\n\nNumber of unique elements to return.')] }],
        uniform:    [{ label: 'random.uniform(a: float, b: float) -> float', doc: '**random.uniform** `-> float`\n\nReturn a random float `N` such that `a ≤ N ≤ b`.', params: [p('a: float','**a** `float`\n\nLower bound.'),p('b: float','**b** `float`\n\nUpper bound.')] }],
        // ─ os.path
        join:       [{ label: 'os.path.join(path: str, *paths: str) -> str', doc: '**os.path.join** `-> str`\n\nJoin path components with the OS separator.\n\n```python\nos.path.join("C:\\\\Users", "file.txt")  # "C:\\Users\\file.txt"\nos.path.join("/home", "user", "docs")   # "/home/user/docs"\n```', params: [p('path: str','**path** `str`\n\nBase path.'),p('*paths: str','**paths** `str`\n\nAdditional path components to join.')] }],
        exists:     [{ label: 'os.path.exists(path: str) -> bool', doc: '**os.path.exists** `-> bool`\n\nReturn `True` if `path` refers to an existing path (file or directory).', params: [p('path: str','**path** `str`\n\nPath to check.')] }],
        basename:   [{ label: 'os.path.basename(path: str) -> str', doc: '**os.path.basename** `-> str`\n\nReturn the final component of `path`.\n\n```python\nos.path.basename("/home/user/file.txt")  # "file.txt"\n```', params: [p('path: str','**path** `str`\n\nFull path string.')] }],
        dirname:    [{ label: 'os.path.dirname(path: str) -> str', doc: '**os.path.dirname** `-> str`\n\nReturn the directory component of `path`.\n\n```python\nos.path.dirname("/home/user/file.txt")  # "/home/user"\n```', params: [p('path: str','**path** `str`\n\nFull path string.')] }],
        splitext:   [{ label: 'os.path.splitext(path: str) -> tuple[str, str]', doc: '**os.path.splitext** `-> tuple[str, str]`\n\nSplit `path` into `(root, ext)` where `ext` includes the dot.\n\n```python\nos.path.splitext("file.tar.gz")  # ("file.tar", ".gz")\n```', params: [p('path: str','**path** `str`\n\nPath to split.')] }],
        // ── Manim mobjects ─────────────────────────────────────────────────
        Circle: [{
            label: 'Circle(radius=1.0, color=WHITE, fill_opacity=0, **kwargs)',
            doc: '**Circle** — `VMobject`\n\nA circle. Set `fill_opacity=1` for a solid disc.\n\n```python\nCircle(radius=2, color=BLUE)\nCircle(radius=1, fill_color=RED, fill_opacity=1)\n```',
            params: [
                p('radius=1.0',       '**radius** `float` *(default: `1.0`)*\n\nRadius in scene units.'),
                p('color=WHITE',      '**color** `Color` *(default: `WHITE`)*\n\nStroke/fill color. Use constants like `BLUE`, `RED`, or hex `"#FF0000"`.'),
                p('fill_opacity=0',   '**fill_opacity** `float` *(default: `0`)*\n\n`0` = hollow outline, `1` = solid disc.'),
                p('**kwargs',         '**kwargs**\n\nExtra VMobject options: `stroke_width`, `fill_color`, `stroke_color`.'),
            ],
        }],
        Square: [{
            label: 'Square(side_length=2.0, color=WHITE, **kwargs)',
            doc: '**Square** — `VMobject`\n\nA square with equal side lengths.\n\n```python\nSquare(side_length=3, color=GREEN)\nSquare().set_fill(BLUE, opacity=0.5)\n```',
            params: [
                p('side_length=2.0',  '**side_length** `float` *(default: `2.0`)*\n\nLength of each side in scene units.'),
                p('color=WHITE',      '**color** `Color` *(default: `WHITE`)*\n\nStroke color.'),
                p('**kwargs',         '**kwargs**\n\nExtra VMobject options: `fill_color`, `fill_opacity`, `stroke_width`.'),
            ],
        }],
        Rectangle: [{
            label: 'Rectangle(width=4.0, height=2.0, color=WHITE, **kwargs)',
            doc: '**Rectangle** — `VMobject`\n\nA rectangle.\n\n```python\nRectangle(width=6, height=3, color=YELLOW)\n```',
            params: [
                p('width=4.0',   '**width** `float` *(default: `4.0`)*\n\nHorizontal size in scene units.'),
                p('height=2.0',  '**height** `float` *(default: `2.0`)*\n\nVertical size in scene units.'),
                p('color=WHITE', '**color** `Color` *(default: `WHITE`)*\n\nStroke color.'),
                p('**kwargs',    '**kwargs**\n\nExtra VMobject options.'),
            ],
        }],
        RoundedRectangle: [{
            label: 'RoundedRectangle(corner_radius=0.5, width=4.0, height=2.0, **kwargs)',
            doc: '**RoundedRectangle** — `VMobject`\n\nA rectangle with rounded corners.\n\n```python\nRoundedRectangle(corner_radius=0.3, width=5, height=2, color=TEAL)\n```',
            params: [
                p('corner_radius=0.5', '**corner_radius** `float` *(default: `0.5`)*\n\nRadius of the rounded corners.'),
                p('width=4.0',         '**width** `float` *(default: `4.0`)*\n\nHorizontal size.'),
                p('height=2.0',        '**height** `float` *(default: `2.0`)*\n\nVertical size.'),
                p('**kwargs',          '**kwargs**\n\nExtra VMobject options.'),
            ],
        }],
        Triangle: [{
            label: 'Triangle(**kwargs)',
            doc: '**Triangle** — `VMobject`\n\nAn equilateral triangle pointing upward.\n\n```python\nTriangle(color=RED, fill_opacity=1)\n```',
            params: [
                p('**kwargs', '**kwargs**\n\nVMobject options: `color`, `fill_color`, `fill_opacity`, `stroke_width`, etc.'),
            ],
        }],
        RegularPolygon: [{
            label: 'RegularPolygon(n=6, **kwargs)',
            doc: '**RegularPolygon** — `VMobject`\n\nA regular n-sided polygon.\n\n```python\nRegularPolygon(n=5, color=PURPLE)  # pentagon\nRegularPolygon(n=8)               # octagon\n```',
            params: [
                p('n=6',      '**n** `int` *(default: `6`)*\n\nNumber of sides.'),
                p('**kwargs', '**kwargs**\n\nVMobject options.'),
            ],
        }],
        Polygon: [{
            label: 'Polygon(*vertices, **kwargs)',
            doc: '**Polygon** — `VMobject`\n\nA closed polygon defined by its corner vertices.\n\n```python\nPolygon(LEFT, RIGHT, UP, color=BLUE)\nPolygon([-1,-1,0], [1,-1,0], [0,1,0])  # triangle\n```',
            params: [
                p('*vertices', '**vertices** `np.ndarray`\n\nTwo or more 3D points as numpy arrays or lists `[x, y, 0]`.'),
                p('**kwargs',  '**kwargs**\n\nVMobject options.'),
            ],
        }],
        Dot: [{
            label: 'Dot(point=ORIGIN, radius=0.08, color=WHITE, **kwargs)',
            doc: '**Dot** — `VMobject`\n\nA small solid dot placed at a point.\n\n```python\nDot(point=RIGHT*2, color=RED)\nDot(ORIGIN, radius=0.15)\n```',
            params: [
                p('point=ORIGIN',  '**point** `np.ndarray` *(default: `ORIGIN`)*\n\nCenter position. Use `ORIGIN`, `LEFT`, `RIGHT`, `UP`, `DOWN`, or `np.array([x,y,0])`.'),
                p('radius=0.08',   '**radius** `float` *(default: `0.08`)*\n\nRadius of the dot.'),
                p('color=WHITE',   '**color** `Color` *(default: `WHITE`)*\n\nFill and stroke color.'),
                p('**kwargs',      '**kwargs**\n\nExtra VMobject options.'),
            ],
        }],
        Arrow: [{
            label: 'Arrow(start=LEFT, end=RIGHT, color=WHITE, buff=0.25, **kwargs)',
            doc: '**Arrow** — `VMobject`\n\nA directed arrow from `start` to `end`.\n\n```python\nArrow(LEFT*2, RIGHT*2, color=YELLOW)\nArrow(ORIGIN, UP*2, buff=0)\n```',
            params: [
                p('start=LEFT',   '**start** `np.ndarray` *(default: `LEFT`)*\n\nStart point (tail of the arrow).'),
                p('end=RIGHT',    '**end** `np.ndarray` *(default: `RIGHT`)*\n\nEnd point (tip of the arrowhead).'),
                p('color=WHITE',  '**color** `Color` *(default: `WHITE`)*\n\nColor of the arrow.'),
                p('buff=0.25',    '**buff** `float` *(default: `0.25`)*\n\nGap between tip and target when referencing a mobject.'),
                p('**kwargs',     '**kwargs**\n\nExtra VMobject options: `stroke_width`, `tip_length`, etc.'),
            ],
        }],
        DoubleArrow: [{
            label: 'DoubleArrow(start=LEFT, end=RIGHT, color=WHITE, **kwargs)',
            doc: '**DoubleArrow** — `VMobject`\n\nAn arrow with arrowheads on both ends.\n\n```python\nDoubleArrow(LEFT*2, RIGHT*2, color=BLUE)\n```',
            params: [
                p('start=LEFT',  '**start** `np.ndarray` *(default: `LEFT`)*\n\nLeft endpoint.'),
                p('end=RIGHT',   '**end** `np.ndarray` *(default: `RIGHT`)*\n\nRight endpoint.'),
                p('color=WHITE', '**color** `Color` *(default: `WHITE`)*\n\nColor.'),
                p('**kwargs',    '**kwargs**\n\nExtra VMobject options.'),
            ],
        }],
        Line: [{
            label: 'Line(start=LEFT, end=RIGHT, color=WHITE, **kwargs)',
            doc: '**Line** — `VMobject`\n\nA straight line segment.\n\n```python\nLine(LEFT*3, RIGHT*3, color=BLUE)\nLine(ORIGIN, UP*2, stroke_width=6)\n```',
            params: [
                p('start=LEFT',  '**start** `np.ndarray` *(default: `LEFT`)*\n\nStart point of the line.'),
                p('end=RIGHT',   '**end** `np.ndarray` *(default: `RIGHT`)*\n\nEnd point of the line.'),
                p('color=WHITE', '**color** `Color` *(default: `WHITE`)*\n\nLine color.'),
                p('**kwargs',    '**kwargs**\n\nExtra VMobject options: `stroke_width`, `stroke_opacity`.'),
            ],
        }],
        DashedLine: [{
            label: 'DashedLine(start=LEFT, end=RIGHT, dash_length=0.05, **kwargs)',
            doc: '**DashedLine** — `VMobject`\n\nA dashed line segment.\n\n```python\nDashedLine(LEFT*2, RIGHT*2, dash_length=0.1, color=GRAY)\n```',
            params: [
                p('start=LEFT',       '**start** `np.ndarray` *(default: `LEFT`)*\n\nStart point.'),
                p('end=RIGHT',        '**end** `np.ndarray` *(default: `RIGHT`)*\n\nEnd point.'),
                p('dash_length=0.05', '**dash_length** `float` *(default: `0.05`)*\n\nLength of each dash segment.'),
                p('**kwargs',         '**kwargs**\n\nExtra VMobject options.'),
            ],
        }],
        Ellipse: [{
            label: 'Ellipse(width=2.0, height=1.0, color=WHITE, **kwargs)',
            doc: '**Ellipse** — `VMobject`\n\nAn ellipse.\n\n```python\nEllipse(width=4, height=2, color=ORANGE)\n```',
            params: [
                p('width=2.0',   '**width** `float` *(default: `2.0`)*\n\nHorizontal diameter.'),
                p('height=1.0',  '**height** `float` *(default: `1.0`)*\n\nVertical diameter.'),
                p('color=WHITE', '**color** `Color` *(default: `WHITE`)*\n\nStroke color.'),
                p('**kwargs',    '**kwargs**\n\nExtra VMobject options.'),
            ],
        }],
        Arc: [{
            label: 'Arc(radius=1.0, start_angle=0, angle=TAU/4, color=WHITE, **kwargs)',
            doc: '**Arc** — `VMobject`\n\nA circular arc.\n\n```python\nArc(radius=2, start_angle=0, angle=PI)    # semicircle\nArc(radius=1, start_angle=PI/4, angle=PI/2)\n```',
            params: [
                p('radius=1.0',      '**radius** `float` *(default: `1.0`)*\n\nRadius of the underlying circle.'),
                p('start_angle=0',   '**start_angle** `float` *(default: `0`)*\n\nStarting angle in radians (0 = rightward, counterclockwise positive).'),
                p('angle=TAU/4',     '**angle** `float` *(default: `TAU/4`)*\n\nAngular span. `PI` = semicircle, `TAU` = full circle.'),
                p('color=WHITE',     '**color** `Color` *(default: `WHITE`)*\n\nArc color.'),
                p('**kwargs',        '**kwargs**\n\nExtra VMobject options.'),
            ],
        }],
        ArcBetweenPoints: [{
            label: 'ArcBetweenPoints(start, end, angle=PI/4, **kwargs)',
            doc: '**ArcBetweenPoints** — `VMobject`\n\nAn arc drawn between two specific points.\n\n```python\nArcBetweenPoints(LEFT, RIGHT, angle=PI/2)\nArcBetweenPoints(ORIGIN, RIGHT*3, angle=-PI/3)\n```',
            params: [
                p('start',       '**start** `np.ndarray`\n\nStart point of the arc.'),
                p('end',         '**end** `np.ndarray`\n\nEnd point of the arc.'),
                p('angle=PI/4',  '**angle** `float` *(default: `PI/4`)*\n\nCurvature angle. Positive = curves counterclockwise. `PI` = semicircle.'),
                p('**kwargs',    '**kwargs**\n\nExtra VMobject options.'),
            ],
        }],
        Vector: [{
            label: 'Vector(direction=RIGHT, color=YELLOW, **kwargs)',
            doc: '**Vector** — `VMobject`\n\nAn arrow from `ORIGIN` to `direction`.\n\n```python\nVector(RIGHT*2, color=BLUE)\nVector([1, 1, 0], color=GREEN)\n```',
            params: [
                p('direction=RIGHT', '**direction** `np.ndarray` *(default: `RIGHT`)*\n\nDirection and magnitude. The arrow tip points here from ORIGIN.'),
                p('color=YELLOW',    '**color** `Color` *(default: `YELLOW`)*\n\nArrow color.'),
                p('**kwargs',        '**kwargs**\n\nExtra VMobject options.'),
            ],
        }],
        Text: [{
            label: 'Text(text: str, font_size=48, color=WHITE, font="", **kwargs)',
            doc: '**Text** — `VMobject`\n\nPango-rendered text. No LaTeX needed — works with Unicode and any system font.\n\n```python\nText("Hello, World!", font_size=36, color=BLUE)\nText("Bold", weight=BOLD)\nText("Mono", font="Consolas")\n```',
            params: [
                p('text: str',     '**text** `str`\n\nThe string to render. Supports Unicode and emoji.'),
                p('font_size=48',  '**font_size** `float` *(default: `48`)*\n\nFont size in points.'),
                p('color=WHITE',   '**color** `Color` *(default: `WHITE`)*\n\nText fill color.'),
                p('font=""',       '**font** `str` *(default: system font)*\n\nFont family name, e.g. `"Arial"`, `"Consolas"`.'),
                p('**kwargs',      '**kwargs**\n\nExtra options: `weight=BOLD`, `slant=ITALIC`, `t2c`, `t2s`, `line_spacing`.'),
            ],
        }],
        MathTex: [{
            label: 'MathTex(*tex_strings: str, color=WHITE, font_size=48, **kwargs)',
            doc: '**MathTex** — `VMobject`\n\nLaTeX math-mode. Strings are joined and wrapped in `$$ … $$`.\n\n```python\nMathTex(r"e^{i\\pi} + 1 = 0")\nMathTex(r"\\int_0^\\infty", r"x^2\\,dx")\nMathTex(r"\\frac{d}{dx}", color=BLUE)\n```',
            params: [
                p('*tex_strings: str', '**tex_strings** `str`\n\nLaTeX math source strings. Multiple strings are concatenated with a space.'),
                p('color=WHITE',       '**color** `Color` *(default: `WHITE`)*\n\nText color.'),
                p('font_size=48',      '**font_size** `float` *(default: `48`)*\n\nFont size in points.'),
                p('**kwargs',          '**kwargs**\n\nExtra options: `substrings_to_isolate`, `tex_to_color_map`.'),
            ],
        }],
        Tex: [{
            label: 'Tex(*tex_strings: str, color=WHITE, font_size=48, **kwargs)',
            doc: '**Tex** — `VMobject`\n\nLaTeX text-mode rendering (not math mode).\n\n```python\nTex(r"Hello \\LaTeX")\nTex(r"$E = mc^2$ is famous", color=YELLOW)\n```',
            params: [
                p('*tex_strings: str', '**tex_strings** `str`\n\nLaTeX source strings (text mode). Multiple strings are concatenated.'),
                p('color=WHITE',       '**color** `Color` *(default: `WHITE`)*\n\nText color.'),
                p('font_size=48',      '**font_size** `float` *(default: `48`)*\n\nFont size.'),
                p('**kwargs',          '**kwargs**\n\nExtra options.'),
            ],
        }],
        MarkupText: [{
            label: 'MarkupText(text: str, color=WHITE, font_size=48, **kwargs)',
            doc: '**MarkupText** — `VMobject`\n\nText with Pango markup for inline styling.\n\n```python\nMarkupText(\'<b>Bold</b> and <i>italic</i>\')\nMarkupText(\'<span color="blue">Blue text</span>\')\n```',
            params: [
                p('text: str',    '**text** `str`\n\nPango markup string. Tags: `<b>`, `<i>`, `<span color="...">`, etc.'),
                p('color=WHITE',  '**color** `Color` *(default: `WHITE`)*\n\nBase text color.'),
                p('font_size=48', '**font_size** `float` *(default: `48`)*\n\nBase font size.'),
                p('**kwargs',     '**kwargs**\n\nExtra options.'),
            ],
        }],
        DecimalNumber: [{
            label: 'DecimalNumber(number=0, num_decimal_places=2, **kwargs)',
            doc: '**DecimalNumber** — `VMobject`\n\nA mobject that displays a decimal number and can be animated.\n\n```python\nn = DecimalNumber(3.14, num_decimal_places=2, color=GOLD)\nself.play(ChangeDecimalPoint(n, 2.72))\n```',
            params: [
                p('number=0',              '**number** `float` *(default: `0`)*\n\nInitial numeric value to display.'),
                p('num_decimal_places=2',  '**num_decimal_places** `int` *(default: `2`)*\n\nDigits after the decimal point.'),
                p('**kwargs',              '**kwargs**\n\nExtra VMobject options: `color`, `font_size`.'),
            ],
        }],
        Integer: [{
            label: 'Integer(number=0, **kwargs)',
            doc: '**Integer** — `VMobject`\n\nA mobject displaying an integer value.\n\n```python\nInteger(42, color=YELLOW)\n```',
            params: [
                p('number=0', '**number** `int` *(default: `0`)*\n\nInitial integer to display.'),
                p('**kwargs', '**kwargs**\n\nExtra VMobject options.'),
            ],
        }],
        NumberPlane: [{
            label: 'NumberPlane(x_range=(-7,7,1), y_range=(-4,4,1), **kwargs)',
            doc: '**NumberPlane** — `VMobject`\n\nA coordinate plane with grid lines and axis labels.\n\n```python\nplane = NumberPlane(x_range=(-5,5,1), y_range=(-3,3,1))\nself.add(plane)\n```',
            params: [
                p('x_range=(-7,7,1)', '**x_range** `tuple` *(default: `(-7, 7, 1)`)*\n\nX-axis range: `(min, max, step)`.'),
                p('y_range=(-4,4,1)', '**y_range** `tuple` *(default: `(-4, 4, 1)`)*\n\nY-axis range: `(min, max, step)`.'),
                p('**kwargs',         '**kwargs**\n\nExtra options: `background_line_style`, `axis_config`, `faded_line_ratio`.'),
            ],
        }],
        Axes: [{
            label: 'Axes(x_range=(-1,10,1), y_range=(-1,10,1), **kwargs)',
            doc: '**Axes** — `VMobject`\n\nX and Y axes for plotting functions and data.\n\n```python\nax = Axes(x_range=(-3,3,1), y_range=(-2,2,1))\ngraph = ax.plot(lambda x: np.sin(x), color=BLUE)\n```',
            params: [
                p('x_range=(-1,10,1)', '**x_range** `tuple` *(default: `(-1, 10, 1)`)*\n\nX-axis range: `(min, max, step)`.'),
                p('y_range=(-1,10,1)', '**y_range** `tuple` *(default: `(-1, 10, 1)`)*\n\nY-axis range: `(min, max, step)`.'),
                p('**kwargs',          '**kwargs**\n\nExtra options: `x_axis_config`, `y_axis_config`, `tips`.'),
            ],
        }],
        ThreeDAxes: [{
            label: 'ThreeDAxes(x_range=(-6,6,1), y_range=(-5,5,1), z_range=(-4,4,1), **kwargs)',
            doc: '**ThreeDAxes** — `VMobject`\n\nX, Y, Z axes for 3D scenes. Use inside a `ThreeDScene`.\n\n```python\nclass MyScene(ThreeDScene):\n    def construct(self):\n        ax = ThreeDAxes()\n        self.set_camera_orientation(phi=75*DEGREES, theta=30*DEGREES)\n        self.add(ax)\n```',
            params: [
                p('x_range=(-6,6,1)', '**x_range** `tuple` *(default: `(-6, 6, 1)`)*\n\nX-axis range.'),
                p('y_range=(-5,5,1)', '**y_range** `tuple` *(default: `(-5, 5, 1)`)*\n\nY-axis range.'),
                p('z_range=(-4,4,1)', '**z_range** `tuple` *(default: `(-4, 4, 1)`)*\n\nZ-axis range.'),
                p('**kwargs',         '**kwargs**\n\nExtra options.'),
            ],
        }],
        NumberLine: [{
            label: 'NumberLine(x_range=(-10,10,1), length=None, **kwargs)',
            doc: '**NumberLine** — `VMobject`\n\nA number line with tick marks and labels.\n\n```python\nnl = NumberLine(x_range=(-5,5,1), length=10)\nself.add(nl)\n```',
            params: [
                p('x_range=(-10,10,1)', '**x_range** `tuple` *(default: `(-10, 10, 1)`)*\n\nRange and step: `(min, max, step)`.'),
                p('length=None',        '**length** `float | None` *(default: `None`)*\n\nTotal length in scene units. `None` = auto-computed from x_range.'),
                p('**kwargs',           '**kwargs**\n\nExtra options: `include_numbers`, `label_direction`, `color`.'),
            ],
        }],
        VGroup: [{
            label: 'VGroup(*vmobjects, **kwargs)',
            doc: '**VGroup** — `VMobject`\n\nGroup multiple VMobjects so they can be transformed as one.\n\n```python\ng = VGroup(circle, square, text)\ng.arrange(RIGHT, buff=0.5)\nself.play(FadeIn(g))\n```',
            params: [
                p('*vmobjects', '**vmobjects** `VMobject`\n\nOne or more VMobjects to group together.'),
                p('**kwargs',   '**kwargs**\n\nExtra VMobject options.'),
            ],
        }],
        Group: [{
            label: 'Group(*mobjects)',
            doc: '**Group** — `Mobject`\n\nGroup any Mobjects (including non-VMobjects like `ImageMobject`).\n\n```python\ng = Group(image, circle)\ng.move_to(ORIGIN)\n```',
            params: [
                p('*mobjects', '**mobjects** `Mobject`\n\nAny Manim mobjects to group.'),
            ],
        }],
        Brace: [{
            label: 'Brace(mobject, direction=DOWN, **kwargs)',
            doc: '**Brace** — `VMobject`\n\nA curly brace that wraps around a mobject.\n\n```python\nbrace = Brace(formula, DOWN)\nlabel = brace.get_text("result")\nself.add(brace, label)\n```',
            params: [
                p('mobject',        '**mobject** `VMobject`\n\nThe mobject to brace.'),
                p('direction=DOWN', '**direction** `np.ndarray` *(default: `DOWN`)*\n\nSide of the mobject. Use `UP`, `DOWN`, `LEFT`, `RIGHT`.'),
                p('**kwargs',       '**kwargs**\n\nExtra VMobject options.'),
            ],
        }],
        SurroundingRectangle: [{
            label: 'SurroundingRectangle(mobject, color=YELLOW, buff=0.1, **kwargs)',
            doc: '**SurroundingRectangle** — `VMobject`\n\nA rectangle fitted tightly around a mobject.\n\n```python\nrect = SurroundingRectangle(formula, buff=0.2, color=RED)\nself.play(Create(rect))\n```',
            params: [
                p('mobject',       '**mobject** `VMobject`\n\nThe mobject to surround.'),
                p('color=YELLOW',  '**color** `Color` *(default: `YELLOW`)*\n\nRectangle stroke color.'),
                p('buff=0.1',      '**buff** `float` *(default: `0.1`)*\n\nPadding between the mobject and rectangle edges.'),
                p('**kwargs',      '**kwargs**\n\nExtra VMobject options.'),
            ],
        }],
        ValueTracker: [{
            label: 'ValueTracker(value=0, **kwargs)',
            doc: '**ValueTracker** — `Mobject`\n\nStores a numeric value. Animate it to drive `add_updater` callbacks.\n\n```python\nvt = ValueTracker(0)\ndot = always_redraw(lambda: Dot(RIGHT * vt.get_value()))\nself.play(vt.animate.set_value(3))\n```',
            params: [
                p('value=0',  '**value** `float` *(default: `0`)*\n\nInitial stored value.'),
                p('**kwargs', '**kwargs**\n\nExtra Mobject options.'),
            ],
        }],
        Matrix: [{
            label: 'Matrix(matrix, **kwargs)',
            doc: '**Matrix** — `VMobject`\n\nA visual matrix with brackets.\n\n```python\nMatrix([[1, 2], [3, 4]])\nMatrix([[r"\\pi", r"e"], [0, 1]])\n```',
            params: [
                p('matrix',   '**matrix** `list[list]`\n\n2D list of numbers or LaTeX strings.'),
                p('**kwargs', '**kwargs**\n\nExtra options: `v_buff`, `h_buff`, `bracket_h_buff`, `element_to_mobject`.'),
            ],
        }],
        // ── Manim animations ───────────────────────────────────────────────
        Create: [{
            label: 'Create(mobject, run_time=1.0, **kwargs)',
            doc: '**Create** — Animation\n\nAnimate drawing the outline and fill of a mobject.\n\n```python\nself.play(Create(circle))\nself.play(Create(square, run_time=2))\n```',
            params: [
                p('mobject',       '**mobject** `VMobject`\n\nThe mobject to draw.'),
                p('run_time=1.0',  '**run_time** `float` *(default: `1.0`)*\n\nDuration in seconds.'),
                p('**kwargs',      '**kwargs**\n\nExtra animation options: `rate_func`, `lag_ratio`.'),
            ],
        }],
        Uncreate: [{
            label: 'Uncreate(mobject, run_time=1.0, **kwargs)',
            doc: '**Uncreate** — Animation\n\nReverse of `Create` — erase the mobject.\n\n```python\nself.play(Uncreate(circle))\n```',
            params: [
                p('mobject',      '**mobject** `VMobject`\n\nThe mobject to erase.'),
                p('run_time=1.0', '**run_time** `float` *(default: `1.0`)*\n\nDuration in seconds.'),
                p('**kwargs',     '**kwargs**\n\nExtra animation options.'),
            ],
        }],
        DrawBorderThenFill: [{
            label: 'DrawBorderThenFill(mobject, run_time=2.0, **kwargs)',
            doc: '**DrawBorderThenFill** — Animation\n\nDraw the border first, then fill the interior.\n\n```python\nself.play(DrawBorderThenFill(square))\n```',
            params: [
                p('mobject',      '**mobject** `VMobject`\n\nThe filled shape to animate.'),
                p('run_time=2.0', '**run_time** `float` *(default: `2.0`)*\n\nTotal duration in seconds.'),
                p('**kwargs',     '**kwargs**\n\nExtra animation options.'),
            ],
        }],
        Write: [{
            label: 'Write(mobject, run_time=None, **kwargs)',
            doc: '**Write** — Animation\n\nAnimate writing text or tracing a path.\n\n```python\nself.play(Write(Text("Hello")))\nself.play(Write(MathTex(r"E=mc^2")))\n```',
            params: [
                p('mobject',         '**mobject** `VMobject`\n\nThe text or path mobject to write.'),
                p('run_time=None',   '**run_time** `float | None` *(default: auto)*\n\nDuration in seconds. `None` = auto-calculated based on mobject size.'),
                p('**kwargs',        '**kwargs**\n\nExtra animation options: `rate_func`, `lag_ratio`.'),
            ],
        }],
        FadeIn: [{
            label: 'FadeIn(mobject, shift=ORIGIN, scale=1.0, **kwargs)',
            doc: '**FadeIn** — Animation\n\nFade a mobject into view, optionally sliding from a direction.\n\n```python\nself.play(FadeIn(circle))\nself.play(FadeIn(text, shift=UP))\nself.play(FadeIn(square, scale=0.5))  # shrink-in\n```',
            params: [
                p('mobject',       '**mobject** `Mobject`\n\nThe mobject to fade in.'),
                p('shift=ORIGIN',  '**shift** `np.ndarray` *(default: `ORIGIN`)*\n\nTranslation applied during the fade. `shift=UP` slides in from below.'),
                p('scale=1.0',     '**scale** `float` *(default: `1.0`)*\n\nScale at which the mobject starts. `< 1` → shrinks in, `> 1` → grows in.'),
                p('**kwargs',      '**kwargs**\n\nExtra animation options.'),
            ],
        }],
        FadeOut: [{
            label: 'FadeOut(mobject, shift=ORIGIN, scale=1.0, **kwargs)',
            doc: '**FadeOut** — Animation\n\nFade a mobject out of view.\n\n```python\nself.play(FadeOut(circle))\nself.play(FadeOut(text, shift=DOWN))\n```',
            params: [
                p('mobject',      '**mobject** `Mobject`\n\nThe mobject to fade out.'),
                p('shift=ORIGIN', '**shift** `np.ndarray` *(default: `ORIGIN`)*\n\nTranslation applied during the fade.'),
                p('scale=1.0',    '**scale** `float` *(default: `1.0`)*\n\nFinal scale at disappearance.'),
                p('**kwargs',     '**kwargs**\n\nExtra animation options.'),
            ],
        }],
        Transform: [{
            label: 'Transform(mobject, target_mobject, **kwargs)',
            doc: '**Transform** — Animation\n\nMorph `mobject` into `target_mobject`. The source **stays** in the scene after the animation.\n\n```python\ncircle = Circle()\nsquare = Square()\nself.add(circle)\nself.play(Transform(circle, square))  # circle is now square-shaped\n```',
            params: [
                p('mobject',         '**mobject** `VMobject`\n\nThe source mobject (modified in place).'),
                p('target_mobject',  '**target_mobject** `VMobject`\n\nThe target shape. Not added to the scene — used as a template only.'),
                p('**kwargs',        '**kwargs**\n\nExtra animation options: `run_time`, `rate_func`, `path_arc`.'),
            ],
        }],
        ReplacementTransform: [{
            label: 'ReplacementTransform(mobject, target_mobject, **kwargs)',
            doc: '**ReplacementTransform** — Animation\n\nMorph `mobject` into `target_mobject`, replacing the source. After the animation only `target_mobject` exists in the scene.\n\n```python\nself.play(ReplacementTransform(eq1, eq2))\n# eq1 is gone, eq2 is now on screen\n```',
            params: [
                p('mobject',        '**mobject** `VMobject`\n\nThe source (removed from scene after animation).'),
                p('target_mobject', '**target_mobject** `VMobject`\n\nThe target (takes the place of source in scene).'),
                p('**kwargs',       '**kwargs**\n\nExtra animation options.'),
            ],
        }],
        TransformFromCopy: [{
            label: 'TransformFromCopy(mobject, target_mobject, **kwargs)',
            doc: '**TransformFromCopy** — Animation\n\nCreate a copy of `mobject` and transform it into `target_mobject`. The original remains unchanged.\n\n```python\nself.play(TransformFromCopy(formula[0], formula[1]))\n```',
            params: [
                p('mobject',        '**mobject** `VMobject`\n\nThe source mobject (untouched; a copy is animated).'),
                p('target_mobject', '**target_mobject** `VMobject`\n\nThe destination for the animated copy.'),
                p('**kwargs',       '**kwargs**\n\nExtra animation options.'),
            ],
        }],
        MoveToTarget: [{
            label: 'MoveToTarget(mobject, **kwargs)',
            doc: '**MoveToTarget** — Animation\n\nMove a mobject to its `.target` attribute.\n\n```python\ncircle.generate_target()\ncircle.target.shift(RIGHT*2).scale(0.5)\nself.play(MoveToTarget(circle))\n```',
            params: [
                p('mobject',  '**mobject** `VMobject`\n\nMobject with a `.target` set via `.generate_target()`.'),
                p('**kwargs', '**kwargs**\n\nExtra animation options.'),
            ],
        }],
        ApplyMethod: [{
            label: 'ApplyMethod(method, *args, **kwargs)',
            doc: '**ApplyMethod** — Animation\n\nAnimate any mobject method that returns self. Prefer `.animate` in modern Manim.\n\n```python\n# Old style:\nself.play(ApplyMethod(circle.shift, RIGHT*2))\n# Modern preferred:\nself.play(circle.animate.shift(RIGHT*2))\n```',
            params: [
                p('method',   '**method** `Callable`\n\nBound method of a Mobject, e.g. `circle.shift`.'),
                p('*args',    '**args**\n\nArguments passed to the method.'),
                p('**kwargs', '**kwargs**\n\nExtra animation options: `run_time`, `rate_func`.'),
            ],
        }],
        Rotate: [{
            label: 'Rotate(mobject, angle, axis=OUT, **kwargs)',
            doc: '**Rotate** — Animation\n\nRotate a mobject by `angle` radians around `axis`.\n\n```python\nself.play(Rotate(square, PI/4))          # 45° in-plane\nself.play(Rotate(cube, PI, axis=RIGHT))  # 3D flip\n```',
            params: [
                p('mobject',    '**mobject** `Mobject`\n\nThe mobject to rotate.'),
                p('angle',      '**angle** `float`\n\nRotation angle in radians. Use `PI`, `TAU`, or `n*DEGREES`.'),
                p('axis=OUT',   '**axis** `np.ndarray` *(default: `OUT`)*\n\nRotation axis. `OUT` = screen-perpendicular (standard 2D). Use `RIGHT`, `UP` for 3D.'),
                p('**kwargs',   '**kwargs**\n\nExtra animation options: `run_time`, `rate_func`, `about_point`.'),
            ],
        }],
        GrowFromCenter: [{
            label: 'GrowFromCenter(mobject, **kwargs)',
            doc: '**GrowFromCenter** — Animation\n\nGrow a mobject outward from its center point.\n\n```python\nself.play(GrowFromCenter(circle))\n```',
            params: [
                p('mobject',  '**mobject** `VMobject`\n\nThe mobject to grow.'),
                p('**kwargs', '**kwargs**\n\nExtra animation options: `run_time`, `rate_func`.'),
            ],
        }],
        GrowFromPoint: [{
            label: 'GrowFromPoint(mobject, point, **kwargs)',
            doc: '**GrowFromPoint** — Animation\n\nGrow a mobject outward from a specific point.\n\n```python\nself.play(GrowFromPoint(text, ORIGIN))\nself.play(GrowFromPoint(arrow, arrow.get_start()))\n```',
            params: [
                p('mobject',  '**mobject** `VMobject`\n\nThe mobject to grow.'),
                p('point',    '**point** `np.ndarray`\n\nThe origin point from which the mobject grows.'),
                p('**kwargs', '**kwargs**\n\nExtra animation options.'),
            ],
        }],
        GrowArrow: [{
            label: 'GrowArrow(arrow, **kwargs)',
            doc: '**GrowArrow** — Animation\n\nAnimate an arrow extending from its tail to its tip.\n\n```python\narrow = Arrow(LEFT, RIGHT)\nself.play(GrowArrow(arrow))\n```',
            params: [
                p('arrow',    '**arrow** `Arrow`\n\nThe Arrow mobject to grow.'),
                p('**kwargs', '**kwargs**\n\nExtra animation options: `run_time`, `rate_func`.'),
            ],
        }],
        SpinInFromNothing: [{
            label: 'SpinInFromNothing(mobject, **kwargs)',
            doc: '**SpinInFromNothing** — Animation\n\nSpin and grow a mobject into existence.\n\n```python\nself.play(SpinInFromNothing(star))\n```',
            params: [
                p('mobject',  '**mobject** `VMobject`\n\nThe mobject to spin in.'),
                p('**kwargs', '**kwargs**\n\nExtra animation options: `run_time`, `angle`.'),
            ],
        }],
        Indicate: [{
            label: 'Indicate(mobject, color=YELLOW, scale_factor=1.2, **kwargs)',
            doc: '**Indicate** — Animation\n\nBriefly scale up and recolor a mobject to draw attention, then revert.\n\n```python\nself.play(Indicate(equation[2]))  # highlight a term\nself.play(Indicate(circle, color=RED, scale_factor=1.5))\n```',
            params: [
                p('mobject',          '**mobject** `VMobject`\n\nThe mobject to highlight.'),
                p('color=YELLOW',     '**color** `Color` *(default: `YELLOW`)*\n\nHighlight color during the indication.'),
                p('scale_factor=1.2', '**scale_factor** `float` *(default: `1.2`)*\n\nHow much to scale up. `1.0` = no size change.'),
                p('**kwargs',         '**kwargs**\n\nExtra animation options: `run_time`, `rate_func`.'),
            ],
        }],
        Flash: [{
            label: 'Flash(point, color=YELLOW, flash_radius=0.3, num_lines=12, **kwargs)',
            doc: '**Flash** — Animation\n\nRadial flash lines emanating from a point (star-burst effect).\n\n```python\nself.play(Flash(dot.get_center(), color=WHITE))\nself.play(Flash(ORIGIN, flash_radius=0.5, num_lines=8))\n```',
            params: [
                p('point',            '**point** `np.ndarray`\n\nCenter point for the flash, e.g. `dot.get_center()`.'),
                p('color=YELLOW',     '**color** `Color` *(default: `YELLOW`)*\n\nColor of the flash lines.'),
                p('flash_radius=0.3', '**flash_radius** `float` *(default: `0.3`)*\n\nRadius to which lines extend.'),
                p('num_lines=12',     '**num_lines** `int` *(default: `12`)*\n\nNumber of radial lines.'),
                p('**kwargs',         '**kwargs**\n\nExtra animation options: `run_time`, `line_stroke_width`.'),
            ],
        }],
        Circumscribe: [{
            label: 'Circumscribe(mobject, shape=Rectangle, color=YELLOW, run_time=1.0, **kwargs)',
            doc: '**Circumscribe** — Animation\n\nDraw a shape around a mobject then fade it out.\n\n```python\nself.play(Circumscribe(formula, shape=Circle, color=RED))\nself.play(Circumscribe(text, run_time=2))\n```',
            params: [
                p('mobject',          '**mobject** `VMobject`\n\nThe mobject to draw around.'),
                p('shape=Rectangle',  '**shape** `type` *(default: `Rectangle`)*\n\nShape class: `Rectangle` or `Circle`.'),
                p('color=YELLOW',     '**color** `Color` *(default: `YELLOW`)*\n\nColor of the circumscribing shape.'),
                p('run_time=1.0',     '**run_time** `float` *(default: `1.0`)*\n\nDuration in seconds.'),
                p('**kwargs',         '**kwargs**\n\nExtra animation options: `fade_in`, `fade_out`, `buff`.'),
            ],
        }],
        ShowPassingFlash: [{
            label: 'ShowPassingFlash(mobject, time_width=0.1, **kwargs)',
            doc: '**ShowPassingFlash** — Animation\n\nA glowing highlight traveling along the length of a path.\n\n```python\nself.play(ShowPassingFlash(circle.copy().set_color(YELLOW), time_width=0.3))\n```',
            params: [
                p('mobject',         '**mobject** `VMobject`\n\nThe path along which the flash travels.'),
                p('time_width=0.1',  '**time_width** `float` *(default: `0.1`)*\n\nFractional length of the visible highlight (0 → point, 1 → full path).'),
                p('**kwargs',        '**kwargs**\n\nExtra animation options: `run_time`, `rate_func`.'),
            ],
        }],
        AnimationGroup: [{
            label: 'AnimationGroup(*animations, lag_ratio=0, **kwargs)',
            doc: '**AnimationGroup** — Animation\n\nRun multiple animations together. Use `lag_ratio` to stagger them.\n\n```python\nself.play(AnimationGroup(FadeIn(a), FadeIn(b)))               # simultaneous\nself.play(AnimationGroup(FadeIn(a), FadeIn(b), lag_ratio=0.5))  # staggered\n```',
            params: [
                p('*animations',  '**animations** `Animation`\n\nTwo or more animation objects to group.'),
                p('lag_ratio=0',  '**lag_ratio** `float` *(default: `0`)*\n\nDelay between starts as a fraction of total run time. `0` = simultaneous, `1` = sequential.'),
                p('**kwargs',     '**kwargs**\n\nExtra options: `run_time`, `rate_func`.'),
            ],
        }],
        Succession: [{
            label: 'Succession(*animations, **kwargs)',
            doc: '**Succession** — Animation\n\nRun animations strictly one after another.\n\n```python\nself.play(Succession(FadeIn(a), Write(b), Create(c)))\n```',
            params: [
                p('*animations', '**animations** `Animation`\n\nAnimations to play in sequence.'),
                p('**kwargs',    '**kwargs**\n\nExtra animation options: `run_time`.'),
            ],
        }],
        LaggedStart: [{
            label: 'LaggedStart(*animations, lag_ratio=0.05, **kwargs)',
            doc: '**LaggedStart** — Animation\n\nStart each animation slightly after the previous one.\n\n```python\nself.play(LaggedStart(*[FadeIn(m) for m in mobjects], lag_ratio=0.1))\n```',
            params: [
                p('*animations',     '**animations** `Animation`\n\nAnimations to stagger.'),
                p('lag_ratio=0.05',  '**lag_ratio** `float` *(default: `0.05`)*\n\nFraction of run_time to wait before starting each subsequent animation.'),
                p('**kwargs',        '**kwargs**\n\nExtra animation options.'),
            ],
        }],
        LaggedStartMap: [{
            label: 'LaggedStartMap(anim_class, mobject, lag_ratio=0.05, **kwargs)',
            doc: '**LaggedStartMap** — Animation\n\nApply an animation class to each sub-mobject of a VGroup with staggered timing.\n\n```python\ntext = Text("Hello")\nself.play(LaggedStartMap(FadeIn, text, lag_ratio=0.1))\n```',
            params: [
                p('anim_class',     '**anim_class** `type`\n\nAnimation class to apply, e.g. `FadeIn`, `Create`.'),
                p('mobject',        '**mobject** `VMobject`\n\nContainer whose sub-mobjects are each animated.'),
                p('lag_ratio=0.05', '**lag_ratio** `float` *(default: `0.05`)*\n\nStagger ratio between sub-animations.'),
                p('**kwargs',       '**kwargs**\n\nExtra options passed to each animation instance.'),
            ],
        }],
        // ── Scene methods ──────────────────────────────────────────────────
        play: [{
            label: 'self.play(*animations, run_time=None, rate_func=smooth, **kwargs)',
            doc: '**self.play** — Scene method\n\nPlay one or more animations. Waits until all are complete.\n\n```python\nself.play(Create(circle))                         # one animation\nself.play(FadeIn(a), FadeOut(b))                  # simultaneously\nself.play(Write(text), run_time=3)                # custom duration\nself.play(circle.animate.shift(RIGHT).scale(2))   # .animate API\n```',
            params: [
                p('*animations',         '**animations** `Animation`\n\nOne or more animation objects to play simultaneously.'),
                p('run_time=None',        '**run_time** `float | None` *(default: auto)*\n\nOverride total duration in seconds.'),
                p('rate_func=smooth',     '**rate_func** `Callable` *(default: `smooth`)*\n\nEasing function: `smooth`, `linear`, `rush_into`, `rush_from`, `there_and_back`, etc.'),
                p('**kwargs',            '**kwargs**\n\nExtra options: `lag_ratio`, `subcaption`.'),
            ],
        }],
        wait: [{
            label: 'self.wait(duration=1, stop_condition=None)',
            doc: '**self.wait** — Scene method\n\nPause the scene for `duration` seconds.\n\n```python\nself.wait()          # 1 second\nself.wait(2.5)       # 2.5 seconds\n```',
            params: [
                p('duration=1',           '**duration** `float` *(default: `1`)*\n\nPause length in seconds.'),
                p('stop_condition=None',  '**stop_condition** `Callable | None` *(default: `None`)*\n\nIf it returns truthy, the wait ends early.'),
            ],
        }],
        add: [{
            label: 'self.add(*mobjects)',
            doc: '**self.add** — Scene method\n\nAdd mobjects to the scene instantly (no animation).\n\n```python\nself.add(circle, text, axes)\n```',
            params: [
                p('*mobjects', '**mobjects** `Mobject`\n\nOne or more mobjects to display.'),
            ],
        }],
        remove: [{
            label: 'self.remove(*mobjects)',
            doc: '**self.remove** — Scene method\n\nRemove mobjects from the scene instantly (no animation).\n\n```python\nself.remove(circle)\nself.remove(a, b, c)\n```',
            params: [
                p('*mobjects', '**mobjects** `Mobject`\n\nOne or more mobjects to remove.'),
            ],
        }],
        // ── Mobject methods ────────────────────────────────────────────────
        move_to: [{
            label: 'mobject.move_to(point_or_mobject, aligned_edge=ORIGIN)',
            doc: '**move_to** — Mobject method\n\nMove the center of this mobject to a point or another mobject\'s position.\n\n```python\ncircle.move_to(ORIGIN)\ncircle.move_to(square)               # same center\ncircle.move_to(square, aligned_edge=UL)  # align corners\n```',
            params: [
                p('point_or_mobject',    '**point_or_mobject** `np.ndarray | Mobject`\n\nDestination point or another mobject.'),
                p('aligned_edge=ORIGIN', '**aligned_edge** `np.ndarray` *(default: `ORIGIN`)*\n\nWhich edge to align. `ORIGIN` = center. Use `UL`, `UR`, `DL`, `DR` for corners.'),
            ],
        }],
        next_to: [{
            label: 'mobject.next_to(mobject_or_point, direction=RIGHT, buff=0.25)',
            doc: '**next_to** — Mobject method\n\nPlace this mobject adjacent to another mobject or point.\n\n```python\nlabel.next_to(circle, DOWN)\nlabel.next_to(circle, UP, buff=0.5)\n```',
            params: [
                p('mobject_or_point', '**mobject_or_point** `Mobject | np.ndarray`\n\nReference mobject or point to place next to.'),
                p('direction=RIGHT',  '**direction** `np.ndarray` *(default: `RIGHT`)*\n\nDirection from the reference. Use `UP`, `DOWN`, `LEFT`, `RIGHT`, or diagonals.'),
                p('buff=0.25',        '**buff** `float` *(default: `0.25`)*\n\nGap between the two mobjects in scene units.'),
            ],
        }],
        shift: [{
            label: 'mobject.shift(*vectors)',
            doc: '**shift** — Mobject method\n\nTranslate the mobject by the sum of one or more vectors.\n\n```python\ncircle.shift(RIGHT * 2)\ncircle.shift(UP + LEFT)\n```',
            params: [
                p('*vectors', '**vectors** `np.ndarray`\n\nOne or more displacement vectors. They are summed together.'),
            ],
        }],
        scale: [{
            label: 'mobject.scale(scale_factor, **kwargs)',
            doc: '**scale** — Mobject method\n\nScale the mobject by `scale_factor` from its center.\n\n```python\ncircle.scale(2)          # double size\ncircle.scale(0.5)        # half size\ncircle.scale(3, about_point=ORIGIN)\n```',
            params: [
                p('scale_factor', '**scale_factor** `float`\n\nMultiplier: `> 1` → larger, `< 1` → smaller.'),
                p('**kwargs',     '**kwargs**\n\nExtra options: `about_point`, `about_edge`.'),
            ],
        }],
        rotate: [{
            label: 'mobject.rotate(angle, axis=OUT, **kwargs)',
            doc: '**rotate** — Mobject method\n\nRotate the mobject by `angle` radians.\n\n```python\nsquare.rotate(PI/4)              # 45°\ncube.rotate(PI/2, axis=RIGHT)    # 3D tilt\n```',
            params: [
                p('angle',    '**angle** `float`\n\nRotation angle in radians. Use `PI`, `TAU`, or `n*DEGREES`.'),
                p('axis=OUT', '**axis** `np.ndarray` *(default: `OUT`)*\n\nRotation axis. `OUT` = standard 2D rotation. Use `RIGHT`, `UP` for 3D.'),
                p('**kwargs', '**kwargs**\n\nExtra options: `about_point`, `about_edge`.'),
            ],
        }],
        set_color: [{
            label: 'mobject.set_color(color=WHITE, family=True)',
            doc: '**set_color** — Mobject method\n\nSet the stroke and fill color of this mobject.\n\n```python\ncircle.set_color(BLUE)\nvgroup.set_color(RED, family=False)  # container only\n```',
            params: [
                p('color=WHITE',  '**color** `Color` *(default: `WHITE`)*\n\nTarget color: constants (`BLUE`, `RED`) or hex `"#FF0000"`.'),
                p('family=True',  '**family** `bool` *(default: `True`)*\n\nIf `True`, also recolor all sub-mobjects.'),
            ],
        }],
        set_opacity: [{
            label: 'mobject.set_opacity(opacity, family=True)',
            doc: '**set_opacity** — Mobject method\n\nSet the overall opacity.\n\n```python\ncircle.set_opacity(0.5)   # semi-transparent\ntext.set_opacity(0)       # invisible\n```',
            params: [
                p('opacity',     '**opacity** `float`\n\nValue between `0` (invisible) and `1` (fully opaque).'),
                p('family=True', '**family** `bool` *(default: `True`)*\n\nIf `True`, also set opacity on all sub-mobjects.'),
            ],
        }],
        to_edge: [{
            label: 'mobject.to_edge(edge, buff=0.5)',
            doc: '**to_edge** — Mobject method\n\nMove the mobject to the specified edge of the frame.\n\n```python\ntitle.to_edge(UP)\nfooter.to_edge(DOWN, buff=0.2)\n```',
            params: [
                p('edge',     '**edge** `np.ndarray`\n\nFrame edge: `UP`, `DOWN`, `LEFT`, or `RIGHT`.'),
                p('buff=0.5', '**buff** `float` *(default: `0.5`)*\n\nGap between the mobject and the frame edge.'),
            ],
        }],
        to_corner: [{
            label: 'mobject.to_corner(corner=DL, buff=0.5)',
            doc: '**to_corner** — Mobject method\n\nMove the mobject to a corner of the frame.\n\n```python\nlogo.to_corner(DR)         # bottom-right\ntitle.to_corner(UL, buff=0.3)\n```',
            params: [
                p('corner=DL', '**corner** `np.ndarray` *(default: `DL`)*\n\nCorner position: `UL`, `UR`, `DL`, `DR`.'),
                p('buff=0.5',  '**buff** `float` *(default: `0.5`)*\n\nGap between the mobject and the corner.'),
            ],
        }],
        align_to: [{
            label: 'mobject.align_to(mobject_or_point, direction)',
            doc: '**align_to** — Mobject method\n\nAlign one edge of this mobject to the corresponding edge of another.\n\n```python\nlabel.align_to(circle, LEFT)   # left edges aligned\nlabel.align_to(circle, UP)     # top edges aligned\n```',
            params: [
                p('mobject_or_point', '**mobject_or_point** `Mobject | np.ndarray`\n\nReference mobject or point.'),
                p('direction',        '**direction** `np.ndarray`\n\nEdge to align: `UP`, `DOWN`, `LEFT`, `RIGHT`.'),
            ],
        }],
        set_fill: [{
            label: 'mobject.set_fill(color=None, opacity=None, family=True)',
            doc: '**set_fill** — Mobject method\n\nSet the interior fill color and/or opacity.\n\n```python\ncircle.set_fill(BLUE, opacity=1)   # solid blue fill\ncircle.set_fill(opacity=0)         # clear fill, keep stroke\n```',
            params: [
                p('color=None',   '**color** `Color | None` *(default: `None`)*\n\nFill color. `None` = keep current color.'),
                p('opacity=None', '**opacity** `float | None` *(default: `None`)*\n\nFill opacity `0–1`. `None` = keep current.'),
                p('family=True',  '**family** `bool` *(default: `True`)*\n\nIf `True`, also apply to all sub-mobjects.'),
            ],
        }],
        set_stroke: [{
            label: 'mobject.set_stroke(color=None, width=None, opacity=None)',
            doc: '**set_stroke** — Mobject method\n\nSet the stroke (outline) color, width, and opacity.\n\n```python\ncircle.set_stroke(RED, width=4)\ncircle.set_stroke(width=0)         # hide stroke\n```',
            params: [
                p('color=None',   '**color** `Color | None` *(default: `None`)*\n\nStroke color.'),
                p('width=None',   '**width** `float | None` *(default: `None`)*\n\nStroke thickness. `0` = invisible.'),
                p('opacity=None', '**opacity** `float | None` *(default: `None`)*\n\nStroke opacity `0–1`.'),
            ],
        }],
        get_center: [{
            label: 'mobject.get_center() -> np.ndarray',
            doc: '**get_center** — Mobject method\n\nReturn the center point as a numpy array `[x, y, z]`.\n\n```python\nc = circle.get_center()  # e.g. array([1., 0., 0.])\nDot(c, color=RED)        # mark the center\n```',
            params: [],
        }],
        copy: [{
            label: 'mobject.copy() -> Mobject',
            doc: '**copy** — Mobject method\n\nReturn a deep copy of this mobject. Changes to the copy don\'t affect the original.\n\n```python\norig = Circle(color=RED)\nclone = orig.copy().shift(RIGHT)\nself.add(orig, clone)  # two separate circles\n```',
            params: [],
        }],
    };

    // Scan backwards from cursor to find the innermost unclosed '('
    // and count commas to determine active parameter index.
    function _getCallInfo(model, position) {
        const lineText = model.getValueInRange({
            startLineNumber: position.lineNumber, startColumn: 1,
            endLineNumber:   position.lineNumber, endColumn: position.column,
        });

        let depth = 0;
        for (let i = lineText.length - 1; i >= 0; i--) {
            const ch = lineText[i];
            if (ch === ')' || ch === ']') { depth++; continue; }
            if (ch === '(' || ch === '[') {
                if (depth === 0 && ch === '(') {
                    // Found the opening paren of the current call
                    const before = lineText.slice(0, i);
                    const m = before.match(/(\w+)\s*$/);
                    if (!m) return null;

                    // Count commas at depth 0 between '(' and cursor → active param
                    let pd = 0, active = 0;
                    for (let j = i + 1; j < lineText.length; j++) {
                        const c = lineText[j];
                        if (c === '(' || c === '[') pd++;
                        else if (c === ')' || c === ']') pd--;
                        else if (c === ',' && pd === 0) active++;
                    }
                    return { fnName: m[1], activeParam: active };
                }
                depth--;
            }
        }
        return null;
    }

    monaco.languages.registerSignatureHelpProvider('python', {
        signatureHelpTriggerCharacters:   ['(', ','],
        signatureHelpRetriggerCharacters: [','],

        provideSignatureHelp(model, position) {
            const info = _getCallInfo(model, position);
            if (!info) return null;

            const sigs = SIG_DB[info.fnName];
            if (!sigs || sigs.length === 0) return null;

            // Pick the overload whose param list is long enough for active index;
            // fall back to the last (most complete) overload.
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
                        label:         sig.label,
                        documentation: { value: sig.doc || '' },
                        // params can be plain strings OR {label, doc} objects
                        parameters: sig.params.map(p =>
                            typeof p === 'string'
                                ? { label: p }
                                : { label: p.label, documentation: p.doc ? { value: p.doc } : undefined }
                        ),
                    })),
                },
                dispose() {},
            };
        },
    });

    console.log('[python-completions] Manim completions + hover docs + signature help registered');
};
