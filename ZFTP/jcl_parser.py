import re
import sys
import os
import time

# add the current directory to the module path if it's not there yet:
module_path = os.path.dirname(__file__)
if module_path not in sys.path:
    sys.path.append(module_path)

import lark

def parse_jcl(jcl):
    statement = []
    substitution = []

    statements = []

    for line in jcl.split('\n'):
        if line[:9] != ' ' * 9:
            if statement:
                # remove "IEFC653I SUBSTITUTION JCL - ":
                statements.append(('\n'.join(statement), ''.join(substitution)[28:]))

                statement = []
                substitution = []
        
        line = line[10:]
        if re.search(r'^//|/\*|XX', line): # statement
            line = line[:72]

            if line[:2] == 'XX':
                line = '//' + line[2:]
            if not line.startswith('//*'):
                statement.append(line)

        else: # IEFC653I SUBSTITUTION JCL
            substitution.append(line)

    if statement:
        # remove "IEFC653I SUBSTITUTION JCL - ":
        statements.append(('\n'.join(statement), ''.join(substitution)[28:]))

        statement = []
        substitution = []

    return statements

grammar = '''
PARAMETER_NAME: /[a-zA-Z0-9.#_-]+/
QUOTED_STRING: "'" ("''" | /[^']/)* "'"
SIMPLE_PARAMETER_VALUE: /[a-zA-Z0-9().#_-]+/

start: parameter_list
parameter_list: parameter? (/,/ parameter?)*
parameter: keyword_parameter | positional_parameter
positional_parameter: parameter_value
parameter_value: QUOTED_STRING | parenthesized_parameter | SIMPLE_PARAMETER_VALUE
keyword_parameter: PARAMETER_NAME /=/ parameter_value?
parenthesized_parameter: /\\(/ parameter_list /\\)/

%ignore " "
'''
parser = lark.Lark(grammar)

def parse_parameters(parameters):
    tree = parser.parse(parameters)

    def traverse_tree(tree):
        if type(tree) is not lark.Tree:
            return tree.value

        jcl = ''
        for node in tree.children:
            if type(node) is lark.Tree:
                jcl += traverse_tree(node)
            else:
                jcl += node.value
        return jcl
            
    parameters = []
    for node in tree.children[0].children:
        node = traverse_tree(node)
        if node == ',':
            continue
        parameters.append(node)

    return parameters

def restore_jcl(jcl):
    statements = parse_jcl(jcl)

    jcl = []
    for statement, substitution in statements:
        match = re.search(r'^(?://|/\*)(\S*) +(\S+)', statement)

        if match.group(2) in ['SET', 'INCLUDE', 'JCLLIB']: # ignore these statements
            continue

        if match.group(2) == 'EXEC': # add step comments
            jcl.append('//*--------------------------------------------------------------------*')
            jcl.append('//* {:66s} *'.format(match.group(1)))
            jcl.append('//*--------------------------------------------------------------------*')

        if substitution:
            if match.group(2) == 'IF':
                parameters = substitution
            else:
                parameters = parse_parameters(substitution)
                parameters = ',\n//         '.join(parameters)

            jcl.append(match.group(0) + '  ' + parameters)
        else:
            jcl.append(statement)

    return '\n'.join(jcl)
