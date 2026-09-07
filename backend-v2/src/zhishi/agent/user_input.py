"""Structured clarification and durable answers for deferred tool execution."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_ai.exceptions import CallDeferred, ModelRetry
from sqlalchemy import update

from zhishi.domain.models import AIUserInput


class QuestionOption(BaseModel):
    model_config = ConfigDict(extra='forbid')
    label: str = Field(min_length=1, max_length=80)
    description: str = Field(default='', max_length=250)


class UserQuestion(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(pattern=r'^[A-Za-z][A-Za-z0-9_-]{0,39}$')
    question: str = Field(min_length=1, max_length=500)
    options: list[QuestionOption] = Field(default_factory=list, max_length=4)
    multi_select: bool = False

    @model_validator(mode='after')
    def unique_options(self):
        if len({option.label for option in self.options}) != len(self.options):
            raise ValueError('选项名称不能重复')
        return self


Questions = Annotated[list[UserQuestion], Field(min_length=1, max_length=3)]


def ask_user(questions: Questions) -> str:
    """向用户收集确实缺少的信息或选择，一次1至3个简短问题。支持选项、多选或自由输入。
    只有答案影响下一步时才提问；明确的要求直接执行。不得用本工具代替操作审批，
    不询问已回答的问题。会话会保存并等待真实回答或明确跳过，不默认选中或自动答复。"""
    if len({question.id for question in questions}) != len(questions):
        raise ModelRetry('每个问题的id必须唯一，请合并重复问题后重新提问。')
    raise CallDeferred()


class UserAnswer(BaseModel):
    model_config = ConfigDict(extra='forbid')
    selected: list[str] = Field(default_factory=list, max_length=4)
    text: str = Field(default='', max_length=4000)


class UserInputReply(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int = Field(ge=0)
    answers: dict[str, UserAnswer] = Field(default_factory=dict)
    skip: bool = False


class UserInputOut(BaseModel):
    id: int
    run_id: str
    call_id: str
    version: int
    status: str
    questions: list[UserQuestion]
    answer: dict


def to_read(row: AIUserInput) -> UserInputOut:
    return UserInputOut(id=row.id, run_id=row.run_id, call_id=row.tool_call_id,
        version=row.version, status=row.status,
        questions=json.loads(row.questions_json), answer=json.loads(row.answer_json))


def answer_request(db, row: AIUserInput, body: UserInputReply) -> AIUserInput:
    questions = [UserQuestion.model_validate(q) for q in json.loads(row.questions_json)]
    if body.skip:
        if body.answers:
            raise ValueError('跳过问题时不能同时提交答案')
        result = {'status': 'skipped', 'answers': [],
                  'note': '用户明确跳过；不要推定任何选项已获选择或任何操作获授权。'}
    else:
        if set(body.answers) != {q.id for q in questions}:
            raise ValueError('请回答每个问题，或明确跳过本组问题')
        answers = []
        for question in questions:
            answer = body.answers[question.id]
            options = {option.label for option in question.options}
            if (any(choice not in options for choice in answer.selected)
                    or len(set(answer.selected)) != len(answer.selected)):
                raise ValueError('提交了无效或重复选项')
            if not question.multi_select and len(answer.selected) > 1:
                raise ValueError('该问题只能选择一项；其他说明请填入文字')
            if not answer.selected and not answer.text.strip():
                raise ValueError('答案不能为空')
            answers.append({'id': question.id, 'question': question.question,
                            'selected': answer.selected, 'text': answer.text.strip()})
        result = {'status': 'answered', 'answers': answers}
    serialized = json.dumps(result, ensure_ascii=False, sort_keys=True)
    if row.status != 'pending':
        if row.status == result['status'] and row.answer_json == serialized:
            return row
        raise RuntimeError('该问题已在另一窗口处理，请同步最新答案')
    claimed = db.execute(update(AIUserInput).where(AIUserInput.id == row.id,
        AIUserInput.status == 'pending', AIUserInput.version == body.version).values(
            status=result['status'], answer_json=serialized,
            version=body.version + 1, resolved_at=datetime.now()))
    if claimed.rowcount != 1:
        db.rollback()
        raise RuntimeError('问题版本已变化，请同步后再提交')
    db.commit()
    db.refresh(row)
    return row
