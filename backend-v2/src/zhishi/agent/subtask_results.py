"""Keep source references and unfinished reads independently of a model summary."""
from zhishi.agent.tool_feedback import FailureTracker, parsed_result


class SubtaskEvidence:
    def __init__(self):
        self.sources = []
        self.reads = []
        self.unresolved = {}

    def record(self, tool, arguments, result):
        value = parsed_result(result)
        key = FailureTracker.key(tool, arguments)
        args = {k:(v[:300] if isinstance(v, str) else v) for k,v in arguments.items()}
        if isinstance(value, dict) and value.get('ok') is False:
            self.unresolved[key] = {'tool':tool, 'arguments':args, 'error':str(value.get('error', '读取失败'))[:250],
                                    'next_call':value.get('next_call')}
            return
        self.unresolved.pop(key, None)
        self.reads.append({'tool':tool, 'arguments':args})
        source = None
        if tool == 'web_fetch' and isinstance(arguments.get('url'), str):
            source = {'kind':'web_page', 'url':arguments['url']}
        elif tool in ('read_material', 'read_research_source'):
            source = {'kind':'material', 'tool':tool, 'arguments':args}
            if isinstance(value, dict):
                source.update({k:value[k] for k in ('file_id','source_id','part','revision','result_ref') if k in value})
        if source and source not in self.sources:
            self.sources.append(source)

    def report(self, summary, *, error=None):
        return {'ok':error is None, 'status':'partial' if self.unresolved or error else 'completed',
                'summary':summary, 'sources':self.sources[:12], 'completed_reads':self.reads[-12:],
                'read_count':len(self.reads), 'unresolved':list(self.unresolved.values())[:8],
                'error':error, 'note':'来源与读取记录由程序收集；搜索摘要不等于已读网页。未解决项不能当作已完成。'}
