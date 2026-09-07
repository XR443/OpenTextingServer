from typing import List

from fastapi import APIRouter
from sqlmodel import select, distinct

from db import SessionDep
from model import UserInfo, User
from model.message import Message
from model.user import map_user_to_info
from security import CurrentUserDep

router = APIRouter(
    prefix="/chats",
    tags=["chats"],
    responses={404: {"description": "Not found"}},
)


@router.get("/", response_model=List[UserInfo])
async def chats(session: SessionDep, current_user: CurrentUserDep):
    chats_with_others = select(distinct(Message.recipient_id)).where(Message.author == current_user)
    chats_with_me = select(distinct(Message.author_id)).where(Message.recipient == current_user)

    chats_with_others = session.exec(chats_with_others).all()
    chats_with_me = session.exec(chats_with_me).all()

    all_chats_select = select(User).where(User.id.in_([*chats_with_me, *chats_with_others]))
    all_chats = session.exec(all_chats_select).all()

    return map(map_user_to_info, all_chats)
