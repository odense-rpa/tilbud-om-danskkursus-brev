from sbsys.manager import SbsysClientManager
from proces.models import Borger
from datetime import datetime
import logging

class SbsysService:
    def __init__(
        self, 
        sbsys: SbsysClientManager
        ):
        self.sbsys = sbsys
    
    
    async def hent_nyeste_relevate_sag(self, borger: Borger) -> dict|None:
        
        sager = await self.sbsys.sager.søg_sager(
            {
                "SagsStatusIds": [
                    6
                ],
                "PrimaerPerson":{
                    "CprNummer":borger.cpr
                },
                "SagsSkabeloner":[
                    "536"
                ]
            }
        )
        
        sag = None
        
        if len(sager) > 1:
            sag = [max(sager, key=lambda s: s["Oprettet"])][0]
        elif len(sager) == 1:
            sag = sager[0]
            
        return sag
    
    async def kontroller_om_sag_har_journalnotat(self, sag:dict) -> bool:
            notater = await self.sbsys.journalnotater.hent_journalnotater_på_sag(sag["Id"])
            
            return any(
                str(notat.get("Overskrift", "")).startswith("Tilbud om danskundervisning sendt")
                for notat in notater
            )

    async def opret_sag(self, sbsys_id:int, sagsbehandler_initialer: str) -> dict:
        
        sagsbehandlere = await self.sbsys.bruger.find_brugere(sagsbehandler_initialer)
        
        if len(sagsbehandlere) > 1:
            sagsbehandler = next(
                (s for s in sagsbehandlere if s["LogonId"].lower() == sagsbehandler_initialer.lower()),
                None
            )
        else:
            sagsbehandler = sagsbehandlere[0]
        
        if sagsbehandler is None:
            raise ValueError("Sagsbehandler ikke fundet")
        
        skabelon = await self.sbsys.sagsskabeloner.hent_sagsskabelon(536)
        
        sagstitel = skabelon["SagsTitel"]
        
        sag = await self.sbsys.sager.opret_sag(sbsys_id, 536, sagsbehandler["Id"], sagstitel)
        
        return sag
    
    async def opret_journalnotat_på_sag(self, sags_id:str, borger: Borger) -> dict:
        
        notat_tekst = (
            f"Vedrørende: {borger.navn} ({borger.cpr})\n\n"
            f"Indrejst: Pgl. er indrejst og registreret på Folkeregisteret.\n\n"
            f"Opholdstilladelse: Opholdstilladelsen er gyldig.\n\n"
            f"Personkreds: I henhold til Lov om danskuddannelsen til voksne udlændinge m.fl."
        )
        
        danske_måneder = [
            "januar", "februar", "marts", "april", "maj", "juni",
            "juli", "august", "september", "oktober", "november", "december"
        ]
        nu = datetime.now()
        notat_overskrift = f"Tilbud om danskundervisning sendt {danske_måneder[nu.month - 1]} {nu.year}"
        
        notat = await self.sbsys.journalnotater.opret_journalnotater(sags_id, notat_overskrift, notat_tekst)
        
        return notat