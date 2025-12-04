from abc import ABC,abstractmethod


from app.config.database import async_db_manager

from app.service.rag_v2.base import Base


class BaseRetrieval(Base):


    @abstractmethod
    async def aretrieval(self,*args,**kwargs):
          #执行检索逻辑
          pass






