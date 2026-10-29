from uuid import UUID
from fastapi import APIRouter, File, HTTPException, Response, UploadFile
from src.exceptions import (
    EmailNotRegisteredException,
    EmailNotRegisteredHTTPException,
    IncorrectPasswordException,
    IncorrectPasswordHTTPException,
    UserAlreadyExistsException,
    UserEmailAlreadyExistsHTTPException,
    PasswordDoNotMatchException,
    PasswordDoNotMatchHTTPException,
    ObjectNotFoundException,
    ObjectNotFoundHTTPException,
    IncorrectTokenException,
    IncorrectTokenHTTPException,
    MyAppException,
    SeveralObjectsFoundException,
    SeveralObjectsFoundHTTPException,
    MyAppHTTPException,
)
from src.schemas.users import (
    UserRequestAdd,
    UserRequestLogIn,
    PasswordResetRequest,
    PasswordChangeRequest,
    UpdateUserRequest,
    TokenResponse,
    RefreshTokenRequest,
    AvatarUploadResponse,
    RegistrationResponse,
)
from src.services.auth import AuthService
from src.api.dependencies.user_id import UserIdDep
from src.api.dependencies.db import DBDep
from src.services.mail import send_email_to_recover_password
from starlette.concurrency import run_in_threadpool
from src.utils.auth_cookies import delete_auth_cookies, set_auth_cookies

router = APIRouter(prefix="/auth", tags=["Авторизация и аутентификация"])


@router.get(
    "/me",
    description="\n            Получение данных пользователя.\n\n            В теле ответа возвращаются данные пользователя (id, username, email, city, company, \n            online, gender, birth_date, phone_number, description, is_active, department, face_to_face, role_id\n            ",
)
async def get_me(db: DBDep, user_id: UserIdDep):
    return await AuthService(db).get_one_or_none_user(id=user_id)


@router.delete("/delete", description="\n            Удаление пользователя.")
async def delete_me(db: DBDep, user_id: UserIdDep):
    return await AuthService(db).delete_user(id=user_id)


@router.post(
    "/register",
    description="\n             Регистрация нового пользователя.\n\n             Входящие данные: email: user@example.com; username: string, birth_date: 2025-09-22; gender: male/female; \n             city: string; phone_number: string; password: string; confirm_password: string\n             ",
    response_model=RegistrationResponse,
)
async def register_user(db: DBDep, data: UserRequestAdd):
    try:
        access_token, refresh_token = await AuthService(db).register_user(data)
    except UserAlreadyExistsException:
        raise UserEmailAlreadyExistsHTTPException
    except PasswordDoNotMatchException:
        raise PasswordDoNotMatchHTTPException
    user_id = UUID(AuthService().decode_token(access_token)["user_id"])
    user = await AuthService(db).get_one_or_none_user(id=user_id)
    return {
        **user.model_dump(),
        "access_token": access_token,
        "refresh_token": refresh_token,
    }


@router.post(
    "/login",
    description="Вход в аккаунт.\n \n             Входящие данные: email: user@example.com; password: string\n             ",
    response_model=TokenResponse,
)
async def login_user(db: DBDep, data: UserRequestLogIn, response: Response):
    try:
        access_token, refresh_token = await AuthService(db).login_user(data)
    except EmailNotRegisteredException:
        raise EmailNotRegisteredHTTPException
    except IncorrectPasswordException:
        raise IncorrectPasswordHTTPException
    set_auth_cookies(response, access_token, refresh_token)
    return {"access_token": access_token, "refresh_token": refresh_token}


@router.post("/token-auth", description="Вход по токену.", response_model=TokenResponse)
async def auth_with_token(db: DBDep, token: str, response: Response):
    try:
        payload = AuthService(db).decode_token(token)
        user_id = UUID(str(payload["user_id"]))
        user = await AuthService(db).get_one_or_none_user(id=user_id)
        if not user:
            raise IncorrectTokenHTTPException
        access_token, refresh_token = AuthService(db).create_tokens(
            {"user_id": str(user.id), "role_id": user.role_id}
        )
        set_auth_cookies(response, access_token, refresh_token)
        return {"access_token": access_token, "refresh_token": refresh_token}
    except (IncorrectTokenException, KeyError, TypeError, ValueError):
        raise IncorrectTokenHTTPException


@router.post("/refresh-token", response_model=TokenResponse)
async def refresh_token(db: DBDep, data: RefreshTokenRequest, response: Response):
    try:
        access_token, refresh_token = await AuthService(db).refresh_tokens(
            data.refresh_token
        )
        set_auth_cookies(response, access_token, refresh_token)
        return {"access_token": access_token, "refresh_token": refresh_token}
    except IncorrectTokenException:
        raise IncorrectTokenHTTPException


@router.post("/logout")
async def logout(response: Response):
    delete_auth_cookies(response)
    return {"status": "OK"}


@router.post("/request-password-reset")
async def password_reset_request(db: DBDep, data: PasswordResetRequest):
    user = await AuthService(db).get_one_or_none_user(email=data.email)
    if not user:
        raise ObjectNotFoundHTTPException
    await run_in_threadpool(send_email_to_recover_password, data.email)
    return {"status": "OK"}


@router.post("/password-reset")
async def password_change(db: DBDep, password_data: PasswordChangeRequest):
    try:
        await AuthService(db).change_password(password_data)
    except IncorrectTokenException:
        raise IncorrectTokenHTTPException
    except PasswordDoNotMatchException:
        raise PasswordDoNotMatchHTTPException
    return {"status": "OK"}


@router.patch(
    "/update",
    description="\n             Редактирование данных пользователя.\n\n             Входящие данные: username: string; description: string; city: string; company: string; online: \n             true/false;  gender: male/female; birth_date: 2025-09-22; phone_number: string\n             ",
)
async def update_user(db: DBDep, user_id: UserIdDep, data: UpdateUserRequest):
    try:
        await AuthService(db).update_user(user_id, data)
        return {"status": "OK"}
    except ObjectNotFoundException:
        raise ObjectNotFoundHTTPException()
    except SeveralObjectsFoundException:
        raise SeveralObjectsFoundHTTPException()
    except IncorrectTokenException:
        raise IncorrectTokenHTTPException()
    except MyAppException as e:
        raise e
    except Exception:
        raise MyAppHTTPException(detail="Не удалось обновить профиль")


@router.patch("/avatar", response_model=AvatarUploadResponse)
async def upload_avatar(db: DBDep, user_id: UserIdDep, avatar: UploadFile = File(...)):
    try:
        content = await avatar.read()
        return await AuthService(db).upload_avatar(
            user_id=user_id,
            filename=avatar.filename,
            content_type=avatar.content_type,
            content=content,
        )
    except ObjectNotFoundException:
        raise ObjectNotFoundHTTPException()
    except ValueError as ex:
        raise HTTPException(status_code=400, detail=str(ex))
    except MyAppException as e:
        raise e
    except Exception:
        raise MyAppHTTPException(detail="Не удалось загрузить аватар")
