import argparse
import ast
import codegen
import os
import signal
import subprocess
from fnmatch import fnmatch
from StringIO import StringIO

TRY_DELETE = (ast.For, ast.Assert, ast.Assign, ast.AugAssign, ast.ClassDef,
              ast.Expr, ast.ExceptHandler, ast.For, ast.FunctionDef,
              ast.Global, ast.If, ast.Import, ast.ImportFrom,
              ast.Print, ast.Raise, ast.TryExcept, ast.TryFinally,
              ast.While, ast.With, )
TRY_DELETE_EXPR = (ast.BoolOp, ast.BinOp, ast.UnaryOp, ast.Lambda, ast.IfExp,
                   ast.Dict, ast.ListComp, ast.GeneratorExp, ast.Yield,
                   ast.Compare, ast.Tuple, )
SPECIAL_CASES = ()
AST_NONE = ast.parse("None").body[0]

class Alarm(Exception):
    pass

def alarm_handler(signum, frame):
    raise Alarm

def run_tests(args):
    "Runs the unit tests"
    
    signal.signal(signal.SIGALRM, alarm_handler)
    signal.alarm(args.timeout)
    tests = subprocess.Popen(args.tests,
                             shell=False,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
    try:
        data, stderr = tests.communicate()
        signal.alarm(0)
        return tests.wait() == 0 and not signal.alarm(0)
    except Alarm:
        tests.kill()
        print "Hit timeout; passed"
        return True # Passed

def perform_replace(args, file, node, base, child, field, index,
                    newnode=AST_NONE):
    "Replaces a node with another"
    
    print "Replacing %s" % str(child)

    oldnodes = None
    if index is not None:
        oldnodes = getattr(node, field)
        newnodes = oldnodes[:]
        newnodes[index] = newnode
        setattr(node, field, newnodes)
    else:
        setattr(node, field, newnode)

    new_source = codegen.to_source(base)
    open(file, mode="w").write(new_source)

    # It's a failure when the tests pass
    if run_tests(args):
        print "Failed"
        log = open("%s.log" % file, mode="a")
        log.write("Failure:\n")
        log.write("Line %d:%d\n" % (child.lineno, child.col_offset))
        log.write("Code:\n")
        log.write(codegen.to_source(child))
        log.write("\n\n\n")
        log.close()
    
    if index is not None:
        setattr(node, field, oldnodes)
    else:
        setattr(node, field, child)
    
def process_node(base, node, args, file, raw):
    "Processes a node in the AST tree"

    fields = list(ast.iter_fields(node))
    for (name, field) in fields:
        if isinstance(field, (str, int)):
            continue
        if not isinstance(field, list):
            if isinstance(field, TRY_DELETE):
                perform_replace(args=args,
                                file=file,
                                node=node,
                                base=base,
                                child=field,
                                field=name,
                                index=None)
            elif isinstance(field, TRY_DELETE_EXPR):
                perform_replace(args=args,
                                file=file,
                                node=node,
                                base=base,
                                child=field,
                                field=name,
                                index=None,
                                newnode=AST_NONE.value)
        else:
            for i in range(len(field)):
                child = field[i]

                # Ignore docstrings
                if i == 1 and \
                   isinstance(node, (ast.FunctionDef,
                                     ast.ClassDef)) and \
                   isinstance(child, ast.Expr):
                    continue

                if isinstance(child, TRY_DELETE):
                    perform_replace(args=args,
                                    file=file,
                                    node=node,
                                    base=base,
                                    child=child,
                                    field=name,
                                    index=i)
                elif isinstance(child, TRY_DELETE_EXPR):
                    perform_replace(args=args,
                                    file=file,
                                    node=node,
                                    base=base,
                                    child=child,
                                    field=name,
                                    index=i,
                                    newnode=AST_NONE.value)
    
    for child in ast.iter_child_nodes(node):
        process_node(base, child, args, file, raw)


def iter_dir(dir, args):
    "Iterates a directory and wreaks havoc"
    
    for item in os.listdir(dir):
        if item.startswith(".") or item.startswith("test_"):
            continue
        item = "%s/%s" % (dir, item)
        
        if os.path.isdir(item):
            iter_dir(item, args)
            continue
        elif not item.endswith(".py"):
            continue

        if any(fnmatch(item, excl) for excl in args.exclude):
            continue

        print "Chaos on %s" % item

        # Get the original copy
        raw = open(item).read()
        p = ast.parse(raw)

        # Run processor on this file
        process_node(p, p, args, item, raw)

        # Replace the original copy
        open(item, mode="w").write(raw)


def main():
    "Initialize the primate"
    
    parser = argparse.ArgumentParser(description="Finding your crappy code")
    parser.add_argument("--code",
                        help="Path to the root of your codebase")
    parser.add_argument("--tests",
                        nargs="*",
                        help="The command to run the test suite")
    parser.add_argument("--exclude",
                        nargs="*",
                        help="File patterns to exclude")
    parser.add_argument("--timeout",
                        type=int,
                        default=20,
                        help="The maximum number of seconds the tests should "
                             "run for before being considered failed")

    args = parser.parse_args()

    if not run_tests(args):
        print "Unit tests do not currently pass. Fix them before chaos"
        return

    iter_dir(args.code, args)

if __name__ == '__main__':
    main()

