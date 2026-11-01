"""CPU Marian inference entry point; input/output JSON over stdin/stdout, no cloud."""
import json
import os
import re
import sys
import time

os.environ['CUDA_VISIBLE_DEVICES'] = ''
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['TOKENIZERS_PARALLELISM'] = 'false'
os.environ.setdefault('OMP_NUM_THREADS','4')


def main():
    sys.stdin.reconfigure(encoding='utf-8')
    sys.stdout.reconfigure(encoding='utf-8')
    import torch
    from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
    data = json.load(sys.stdin)
    torch.set_num_threads(4)
    started = time.monotonic()
    tokenizer = AutoTokenizer.from_pretrained(data['model_dir'],local_files_only=True)
    model = AutoModelForSeq2SeqLM.from_pretrained(data['model_dir'],local_files_only=True,
        use_safetensors=False).to('cpu').eval()
    def run(text: str) -> str:
        # Translate clauses, keeping prompt weights, tags and already-English clauses intact.
        # Keep already-English art terms verbatim; MT must not reinterpret them.
        pieces = re.split(r'("[^"\n]*"|“[^”\n]*”|[\u3400-\u9fff]+)',text)
        result = []
        with torch.inference_mode():
            for piece in pieces:
                if not re.fullmatch(r'[\u3400-\u9fff]+',piece):
                    result.append(piece); continue
                encoded = tokenizer(piece,return_tensors='pt',truncation=False)
                if encoded['input_ids'].shape[-1]>480:
                    raise ValueError('单段描述过长，请用逗号或句号分段。')
                tokens = model.generate(**encoded,max_new_tokens=512,num_beams=4,do_sample=False)
                result.append(tokenizer.decode(tokens[0],skip_special_tokens=True))
        return ''.join(result)
    result = {'positive':run(data['positive']),'negative':run(data['negative']),
        'translated':True,'model':'Helsinki-NLP/opus-mt-zh-en','device':'cpu',
        'seconds':round(time.monotonic()-started,3)}
    print(json.dumps(result,ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
