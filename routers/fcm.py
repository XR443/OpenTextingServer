from fastapi import APIRouter

from db import SessionDep
from model.fcm import FCMRegisterResponse, FCMRegisterRequest, FCMTokenDB
from security import CurrentUserDep

router = APIRouter(
    prefix="/fcm",
    tags=["fcm"],
    responses={404: {"description": "Not found"}},
)
@router.post("/register", response_model=FCMRegisterResponse)
async def register_fcm(
        request: FCMRegisterRequest,
        session: SessionDep,
        current_user: CurrentUserDep,
):
    registered = 0
    failed = []

    for account_id in request.account_ids:
        try:
            # Проверяем существует ли уже такая связка
            existing = session.query(FCMTokenDB).filter(
                FCMTokenDB.account_id == account_id,
                FCMTokenDB.fcm_token == request.fcm_token
            ).first()

            if not existing:
                token = FCMTokenDB(
                    account_id=account_id,
                    fcm_token=request.fcm_token
                )
                session.add(token)
                registered += 1
            else:
                registered += 1  # уже существует

            session.commit()

        except Exception as e:
            session.rollback()
            failed.append(account_id)

    return FCMRegisterResponse(
        success=len(failed) == 0,
        registered=registered,
        failed=failed
    )