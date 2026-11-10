#!/usr/bin/env python3
"""Copy the current experiment properties for one isolated SCOPE diagnostic."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import re
import shlex

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iteration', type=int, default=13)
    args=parser.parse_args()
    if args.iteration < 1:
        parser.error('iteration must be positive')
    root=Path(__file__).resolve().parent.parent
    config=root/'ThreeBrains/scripts/sample_app5/config'
    source=config/'default_config.properties'
    text=source.read_text(encoding='utf-8')
    changes={'orchestrator_policies':'SCOPE',
             'min_number_of_mobile_devices':'1200',
             'max_number_of_mobile_devices':'1200'}
    for key,value in changes.items():
        pattern=rf'(?m)^[ \t]*{re.escape(key)}[ \t]*=[^\r\n]*'
        if len(re.findall(pattern,text))!=1:
            raise ValueError(f'Expected exactly one active {key} setting in {source}')
        text=re.sub(pattern,f'{key}={value}',text)
    token=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    destination=config/f'scope_diagnostic_1200_{token}.properties'
    destination.write_text(text,encoding='utf-8')
    output=root/f'ThreeBrains/revision_results/scope_diagnostic_{token}'/f'ite{args.iteration}'
    output.mkdir(parents=True,exist_ok=False)
    program_args=[str(destination),str(config/'edge_devices.xml'),
                  str(config/'applications.xml'),str(output),str(args.iteration)]
    print('Created an isolated diagnostic configuration. Original properties unchanged.')
    print('Policy: SCOPE; devices: 1200; duration and other simulation settings preserved.')
    print('Start scope_diagnostic_service.py with your existing SCOPE environment variables.')
    print('Java working directory:',root)
    print('\nPaste this single line into Java Arguments:\n')
    print(shlex.join(program_args))
    print('\nJava output:',output)
    print('Flask diagnostics: FLaskAPIs/revision_results/scope_diagnostic/<session>/')
    print('Keep this run separate from final evaluation and timing measurements.')

if __name__=='__main__':
    main()
