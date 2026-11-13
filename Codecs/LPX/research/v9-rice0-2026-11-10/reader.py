"""Create the source-frozen experimental C/ASM reader without editing production.

Bit64 changes only delta-spectrum Rice coding; all recording parameters remain
in the header/payload. Production admission has not been granted. The same
generated source selects C by default or ASM through the existing explicit
architecture/backend defines. No compact error check is removed here.
"""
import hashlib
from pathlib import Path
import shutil
import subprocess

ACTIVE=Path(__file__).resolve().parents[2]/'01_ACTIVE_Q0_CODEC'
BASE_REVISION='393b2de271568890d7b483f7602a2f59452d1a68'
BASE_CORE_SHA256='1df98b18d5443c85a427d77725a794f1ae7293b71c88baff000e20b70bc516b6'
EXPERIMENT_CORE_SHA256='3316eb2ef48f1f3a0662b63e5787fa924330f5e5c96a9de53a1fbbc68c867e16'


def frozen_git(*arguments):
    repo=ACTIVE.parents[2]
    attempts=[['git','-C',str(repo),*arguments]]
    # Windows-created worktrees use Windows gitdir paths. WSL can call the
    # native Git executable without changing repository metadata.
    if str(repo).startswith('/mnt/') and shutil.which('git.exe'):
        parts=repo.parts
        win=parts[2].upper()+':/'+ '/'.join(parts[3:])
        attempts.append(['git.exe','-C',win,*arguments])
    for command in attempts:
        result=subprocess.run(command,capture_output=True)
        if result.returncode==0:return result.stdout
    raise RuntimeError('Git and the frozen baseline revision are required for this research reader')


def make_reader_tree(destination):
    """Copy src into an empty destination and apply the two reviewed changes."""
    destination=Path(destination)
    prefix=ACTIVE.relative_to(ACTIVE.parents[2]).as_posix()+'/src/'
    original={name.decode():frozen_git('show',BASE_REVISION+':'+prefix+name.decode())
              for name in frozen_git('ls-tree','-r','--name-only','-z',BASE_REVISION+':'+prefix.rstrip('/')).split(b'\0') if name}
    source=original['Lpx4HybridCore.cpp'].decode('utf-8').replace('\r\n','\n')
    if hashlib.sha256(source.encode()).hexdigest()!=BASE_CORE_SHA256:
        raise ValueError('Re-review the experiment against the changed production reader')
    edits=[
        ('#if LPX4_COMPACT_ONLY\n#if LPX4_HAS_SPARSE80\n const bool sparse80=',
         '#if LPX4_COMPACT_ONLY\n const uint8_t supportedFlags=flags&(LPX4_COMPACT_VERSION==9?191:255);\n#if LPX4_HAS_SPARSE80\n const bool sparse80='),
        ('&& flags==15;', '&& supportedFlags==15;'),
        ('(version!=LPX4_COMPACT_VERSION || ((flags&127)!=4 && (flags&127)!=6))',
         '(version!=LPX4_COMPACT_VERSION || ((supportedFlags&127)!=4 && (supportedFlags&127)!=6))'),
        ('     const uint8_t k=bits-4-(uint8_t)delta;',
         '#if LPX4_COMPACT_VERSION == 9\n     const uint8_t k=(delta && (LPX4_SPEECH_FLAGS&64))?0:bits-4-(uint8_t)delta;\n#else\n     const uint8_t k=bits-4-(uint8_t)delta;\n#endif'),
    ]
    for before,after in edits:
        if source.count(before)!=1:raise ValueError('Experimental reader anchor changed')
        source=source.replace(before,after)
    if hashlib.sha256(source.encode()).hexdigest()!=EXPERIMENT_CORE_SHA256:
        raise ValueError('Experimental source differs from the measured prototype')
    destination.mkdir(parents=True,exist_ok=False)
    for name,data in original.items():
        path=destination/name;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(data)
    (destination/'Lpx4HybridCore.cpp').write_text(source,encoding='utf-8',newline='\n')
    return destination
