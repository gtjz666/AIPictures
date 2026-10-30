"""Best-effort, ID-scoped cancellation that can outlive the closing GUI."""
import argparse
from .engine import ComfyClient
from .storage import write_json


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url',required=True)
    p.add_argument('--prompt-id',action='append',required=True)
    p.add_argument('--report',required=True)
    args=p.parse_args();client=ComfyClient(args.url);records=[]
    for pid in dict.fromkeys(args.prompt_id):
        try:
            client.cancel(pid)
            records.append({'prompt_id':pid,'cancel_request_sent':True})
        except Exception as exc:
            records.append({'prompt_id':pid,'cancel_request_sent':False,'error':str(exc)})
    write_json(args.report,{'url':client.url,'tasks':records,'backend_terminated':False})


if __name__=='__main__':main()
