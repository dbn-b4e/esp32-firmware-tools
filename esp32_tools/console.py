"""Keep diagnostic output usable on UTF-8 and legacy Windows consoles."""
import builtins
import sys


def safe_print(*values, **kwargs):
    stream=kwargs.get('file') or sys.stdout
    encoding=getattr(stream,'encoding',None) or 'utf-8'
    text=[str(value).encode(encoding,errors='replace').decode(encoding) for value in values]
    builtins.print(*text,**kwargs)
