import uuid
from typing import Tuple
from itsdangerous import URLSafeTimedSerializer, BadData
from fastapi import HTTPException
import jwt
from datetime import datetime, timezone, timedelta
from pathlib import Path
from src.config import settings
from src.services.base import BaseService
from src.exceptions import (
    IncorrectTokenException,
    EmailNotRegisteredException,
    IncorrectPasswordException,
    ObjectAlreadyExistsException,
    UserAlreadyExistsException,
    PasswordDoNotMatchException,
    ObjectNotFoundException,
)
from src.schemas.users import (
    AvatarUploadResponse,
    UserRequestAdd,
    UserAdd,
    UserRequestLogIn,
    PasswordChangeRequest,
    HashedPassword,
    UpdateUserRequest,
)

serializer = URLSafeTimedSerializer(
    settings.JWT_SECRET_KEY, salt="compas-password-reset-v1"
)


class AuthService(BaseService):
    allowed_avatar_extensions = {".jpg", ".jpeg", ".png", ".webp"}
    allowed_avatar_content_types = {"image/jpeg", "image/png", "image/webp"}

    def create_tokens(self, data: dict) -> Tuple[str, str]:
        to_encode = data.copy()
        access_token_expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
        to_encode_access = to_encode.copy()
        to_encode_access.update({"exp": access_token_expire})
        access_token = jwt.encode(
            to_encode_access, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
        )
        refresh_token_expire = datetime.now(timezone.utc) + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        )
        to_encode_refresh = to_encode.copy()
        to_encode_refresh.update({"exp": refresh_token_expire})
        refresh_token = jwt.encode(
            to_encode_refresh,
            settings.JWT_REFRESH_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )
        return (access_token, refresh_token)

    def hash_password(self, password: str) -> str:
        import bcrypt

        encoded = password.encode("utf-8")
        if len(password) < 8 or len(encoded) > 72:
            raise HTTPException(
                400, "Пароль должен содержать от 8 символов и не более 72 байт"
            )
        return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode()

    def verify_password(self, plain_password, hashed_password):
        import bcrypt

        try:
            return len(plain_password.encode("utf-8")) <= 72 and bcrypt.checkpw(
                plain_password.encode("utf-8"), hashed_password.encode()
            )
        except (TypeError, ValueError, AttributeError):
            return False

    def decode_token(self, token: str, is_refresh: bool = False) -> dict:
        try:
            secret_key = (
                settings.JWT_REFRESH_SECRET_KEY
                if is_refresh
                else settings.JWT_SECRET_KEY
            )
            return jwt.decode(token, secret_key, algorithms=[settings.JWT_ALGORITHM])
        except jwt.exceptions.DecodeError:
            raise IncorrectTokenException
        except jwt.ExpiredSignatureError:
            raise IncorrectTokenException("Token expired")

    async def register_user(self, data: UserRequestAdd) -> Tuple[str, str]:
        if data.password != data.confirm_password:
            raise PasswordDoNotMatchException
        hashed_password = self.hash_password(data.password)
        new_user_data = UserAdd(
            **data.model_dump(exclude={"password", "confirm_password"}),
            hashed_password=hashed_password,
            role_id=1,
            id=uuid.uuid4(),
        )
        try:
            await self.db.users.add(new_user_data)
            await self.db.commit()
        except ObjectAlreadyExistsException as ex:
            raise UserAlreadyExistsException from ex
        return self.create_tokens(
            {"user_id": str(new_user_data.id), "role_id": new_user_data.role_id}
        )

    async def login_user(self, data: UserRequestLogIn) -> Tuple[str, str]:
        user = await self.db.users.get_user_with_hashed_password(email=data.email)
        if not user:
            raise EmailNotRegisteredException
        if not self.verify_password(data.password, user.hashed_password):
            raise IncorrectPasswordException
        return self.create_tokens({"user_id": str(user.id), "role_id": user.role_id})

    async def refresh_tokens(self, refresh_token: str) -> Tuple[str, str]:
        try:
            payload = self.decode_token(refresh_token, is_refresh=True)
            user_id = uuid.UUID(str(payload["user_id"]))
            user = await self.db.users.get_one_or_none(id=user_id)
            if not user:
                raise IncorrectTokenException("User not found")
            return self.create_tokens(
                {"user_id": str(user.id), "role_id": user.role_id}
            )
        except Exception as e:
            raise IncorrectTokenException(str(e))

    async def get_one_or_none_user(self, **filter_by):
        return await self.db.users.get_one_or_none(**filter_by)

    async def delete_user(self, id):
        await self.db.users.delete(id=id)
        return {"status": "OK"}

    async def change_password(self, password_data: PasswordChangeRequest):
        try:
            email = serializer.loads(password_data.token, max_age=3600)
        except BadData:
            raise IncorrectTokenException
        if password_data.password != password_data.confirm_new_password:
            raise PasswordDoNotMatchException
        hashed_password = self.hash_password(password_data.password)
        _hashed_password = HashedPassword(hashed_password=hashed_password)
        await self.db.users.edit(_hashed_password, exclude_unset=True, email=email)
        await self.db.commit()

    async def update_user(self, user_id: uuid.UUID, data: UpdateUserRequest):
        user = await self.db.users.get_one_or_none(id=user_id)
        if not user:
            raise ObjectNotFoundException("User not found")
        await self.db.users.edit(data, exclude_unset=True, id=user_id)
        await self.db.commit()

    async def upload_avatar(
        self,
        user_id: uuid.UUID,
        filename: str | None,
        content_type: str | None,
        content: bytes,
    ) -> AvatarUploadResponse:
        user = await self.db.users.get_one_or_none(id=user_id)
        if not user:
            raise ObjectNotFoundException("User not found")
        if not filename:
            raise ValueError("Filename is required")
        if not content:
            raise ValueError("Avatar file is empty")
        suffix = Path(filename).suffix.lower()
        if suffix not in self.allowed_avatar_extensions:
            raise ValueError("Unsupported avatar file extension")
        if content_type not in self.allowed_avatar_content_types:
            raise ValueError("Unsupported avatar content type")
        avatars_dir = Path(__file__).resolve().parent.parent / "images" / "avatars"
        avatars_dir.mkdir(parents=True, exist_ok=True)
        stored_name = f"{user_id}_{uuid.uuid4().hex}{suffix}"
        stored_path = avatars_dir / stored_name
        stored_path.write_bytes(content)
        avatar_link = f"/images/avatars/{stored_name}"
        await self.db.users.edit(
            UpdateUserRequest(avatar_link=avatar_link), exclude_unset=True, id=user_id
        )
        await self.db.commit()
        return AvatarUploadResponse(avatar_link=avatar_link)
