import pymssql
from datetime import datetime, timedelta
from typing import cast


class DWHService:
    def __init__(
        self,
        username: str,
        password: str,
        server: str,
        database: str
        ):   
        self.username = username
        self.password = password
        self.server = server
        self.database = database
        self.connection = None
    
    def _ensure_connection(self):
        if not self.connection:
            self.connection = pymssql.connect(
                server=self.server,
                user=self.username,
                password=self.password,
                database=self.database
            )

    def __enter__(self):
        self._ensure_connection()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.connection:
            self.connection.close()
            self.connection = None
        return False

    def hent_borgere(self) -> list[dict]:
        if self.connection is None:
            raise RuntimeError("Failed to establish database connection.")
        dato = (datetime.today() - timedelta(days=60)).strftime("%Y-%m-%d")
        query = f"""SELECT [Cpr]
      ,[Adresseringsnavn]
      ,[Standardadresse]
      ,[Postnr]
      ,[Postdistrikt]
      ,[Land_statsborger]
      ,[Dato_Ajourfoert]
      ,[Alder_aar]
      ,[Land_indrejst_fra]
       FROM [{self.database}].[dbo].[tilbud_danskundervisning]
       WHERE [Dato_Ajourfoert] >= '{dato}' OR [Dato_ophold_start] >= '{dato}'""" 

        cursor = self.connection.cursor(as_dict=True)
        cursor.execute(query)
        results = cast(list[dict], cursor.fetchall() or [])
        cursor.close()
        
        return results
    
    def hent_adresser_på_borger(self, cpr:str) -> list[dict]:
        if self.connection is None:
            raise RuntimeError("Failed to establish database connection.")
        
        cpr = cpr.replace("-", "")
        query = f"""SELECT
       [Standardadresse]
      ,[Aktuel]
       FROM [{self.database}].[dbo].[adresse_historik_kommune_kendt]
       WHERE Cpr='{cpr}'"""

        cursor = self.connection.cursor(as_dict=True)
        cursor.execute(query)
        results = cast(list[dict], cursor.fetchall() or [])
        cursor.close()

        return results
        