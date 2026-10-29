from src.models.clients import ClientsOrm
from src.repositories.base import BaseRepository
from src.repositories.mappers.mappers import ClientsDataMapper


class ClientsRepository(BaseRepository):
    model = ClientsOrm
    mapper = ClientsDataMapper
