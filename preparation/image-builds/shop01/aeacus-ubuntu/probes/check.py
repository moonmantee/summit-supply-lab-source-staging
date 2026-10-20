#!/usr/bin/env python3
"""Single-objective CLI for Aeacus; stdout is always a non-secret token."""
import sys
import access
import defense
import pam
import permissions
import forensics
import web

def registry():
    modules=(access,pam,defense,permissions,web,forensics)
    table={}
    for module in modules:
        for issue in module.ISSUES:
            if issue in table: raise ValueError('Duplicate probe identifier')
            table[issue]=module.check
    if set(table)!=set(range(1,41)): raise ValueError('Incomplete probe registry')
    return table

def main():
    try:
        if len(sys.argv)!=2: raise ValueError('Expected one identifier')
        issue=int(sys.argv[1]); value=registry()[issue](issue)
        if type(value) is not bool: raise ValueError('Non-boolean probe result')
        print('PASS' if value else 'FAIL')
        return 0
    except Exception:
        # Never include exception messages: evaluated inputs can contain secrets.
        print('ERROR'); return 1

if __name__=='__main__': sys.exit(main())
