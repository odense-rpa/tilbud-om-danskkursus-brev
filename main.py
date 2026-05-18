import asyncio
import logging
import sys
from datetime import datetime
import os
from pathlib import Path
import argparse

from automation_server_client import AutomationServer, Workqueue, WorkItemError, Credential, WorkItemStatus
from sbsys.manager import SbsysClientManager
import sbsip
from datafordeler import Datafordeler
from proces.models import Borger
from odk_tools.tracking import Tracker
from odk_tools.reporting import report
from odk_tools import word
from proces.dwh_service import DWHService
from proces.sbsys_service import SbsysService
from proces.brev_service import BrevService

proces_navn = "Tilbud om danskkursus"
dwh_service: DWHService
sbsys: SbsysClientManager
sbsys_service: SbsysService
fordeler: Datafordeler


async def populate_queue(workqueue: Workqueue):
    logger = logging.getLogger(__name__)

    with dwh_service:
        borgere = dwh_service.hent_borgere()
    
    if borgere is None:
        raise ValueError("Listen af borgere var tom")
    
    for borger in borgere:
        
        borger_obj = Borger(
            cpr=borger["Cpr"],
            navn=borger["Adresseringsnavn"],
            adresse=borger["Standardadresse"],
            postnr=borger["Postnr"],
            by=borger["Postdistrikt"],
            statsborgerskab=borger["Land_statsborger"],
            #Indrejsedato sættes til dato_ajourført af historiske årsager, det er videreført fra BP
            indrejsedato=str(borger["Dato_Ajourfoert"])
        )
        
        if workqueue.get_item_by_reference(borger_obj.cpr, WorkItemStatus.COMPLETED) == []:
            workqueue.add_item(borger_obj.model_dump(), borger_obj.cpr)    


async def process_workqueue(workqueue: Workqueue, fil_sti:str):
    logger = logging.getLogger(__name__)
    with dwh_service:
        async with sbsys:
            for item in workqueue:
                with item:
                    borger: Borger = Borger.model_validate(item.data)
                    try:
                        #Tjek om borger har flere adresser
                        adresser = dwh_service.hent_adresser_på_borger(borger.cpr)
                        if len(adresser) > 1:
                            logger.info("Mere end 1 adresse fundet på borger, kontrollerer om de har haft boligplacering")
                            if any(adresse["Standardadresse"] == "Boligplacering" for adresse in adresser):
                                logger.info("Borger har haft boligplacering, de anses derfor som flygtning og skal derfor ikke have brev, går videre til næste ogpave")
                                continue
                            raise WorkItemError("Flere adresser fundet. Borger har haft bopæl i DK før")
                            
                        #Opret borger i Sbsys
                        sbsys_borger = await sbsys.borger.opret_borger(borger.cpr)
                        
                        if sbsys_borger is None:
                            logger.info("Borger ikke oprettet, ligger opgaven til manuel behandling")
                            raise WorkItemError("SBSYS-fejl: person kunne ikke oprettes i SBSYS, person har muligvis midlertidigt cprnr")
                            
                        #Tjek om borger allerede har indrejsesag
                        sag = await sbsys_service.hent_nyeste_relevate_sag(borger)
                        if sag is not None:
                            logger.info("Borger har allerede sag, kontrollere om notat er på sagen")
                            if (await sbsys_service.kontroller_om_sag_har_journalnotat(sag)):
                                logger.info("Borger har notat på sagen, alt godt, går videre til næste opgave")
                                continue
                            raise WorkItemError("Borger har indrejsesag, men har ikke notat, har muligvis allerede fået brev")
                        
                        weekday = datetime.today().weekday()
                        if weekday in (1, 3):  # Tuesday, Thursday
                            sagsbehandler_initialer = "bwi"
                        elif weekday in (0, 2, 4):  # Monday, Wednesday, Friday
                            sagsbehandler_initialer = "ejoe"
                        else:
                            raise WorkItemError("Processen køres på en weekenddag, hvilket ikke er tilladt")
                        
                        #Opretter sag på borger
                        sag = await sbsys_service.opret_sag(sbsys_borger["Id"], sagsbehandler_initialer)
                        
                        BrevService.flet_og_send_brev(borger, fil_sti, fordeler)
                        
                        try:
                            await sbsys_service.opret_journalnotat_på_sag(sag["Id"], borger)
                        except:
                            raise WorkItemError("SBSYS-fejl: Journalnotat ikke oprettet")
                        
                        report(
                                "tilbud_om_danskkursus_brev",
                                "Brev sendt",
                                json={
                                    "Cpr": borger.cpr,
                                    "Navn": borger.navn,
                                    "Statsborgerskab": borger.statsborgerskab,
                                    "Indrejsedato": borger.indrejsedato,
                                    "Handlinger": "Brev sendt til borger og journalnotat oprettet"
                                }
                            )
                        tracker.track_task(proces_navn)
                        
                    except WorkItemError as e:
                        # A WorkItemError represents a soft error that indicates the item should be passed to manual processing or a business logic fault
                        report(
                            "tilbud_om_danskkursus_brev",
                            "Manuel",
                            json={
                                    "Cpr": borger.cpr,
                                    "Navn": borger.navn,
                                    "Statsborgerskab": borger.statsborgerskab,
                                    "Indrejsedato": borger.indrejsedato,
                                    "Manuel årsag": str(e)
                            }
                        )
                        tracker.track_partial_task(proces_navn)
                        
                    except Exception as e:
                        
                        report(
                            "tilbud_om_danskkursus_brev",
                            "Manuel",
                            json={
                                    "Cpr": borger.cpr,
                                    "Navn": borger.navn,
                                    "Statsborgerskab": borger.statsborgerskab,
                                    "Indrejsedato": borger.indrejsedato,
                                    "Manuel årsag": str(e)
                            }
                        )
                        logger.error(f"Error processing item: {borger.cpr}. Error: {e}")
                        item.fail(str(e))
                    


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ats = AutomationServer.from_environment()
    workqueue = ats.workqueue()

    # Initialize external systems for automation here..
    dwh_creds = Credential.get_credential("Odense SQL Server")
    sbsys_credential = Credential.get_credential("SBSYS - produktion")
    sbsip_credential = Credential.get_credential("SBSip - produktion")
    
    parser = argparse.ArgumentParser(description=proces_navn)
    parser.add_argument(
        "--word-template",
        default="Danish Language Course.docx",
        help="Path to the Word template for letter generation (default: ./Tildeling af sygeplejeartikler til terminale borgere.docx)",
    )
    args = parser.parse_args()
    
    certifikat_sti = os.getenv("CERTIFIKATER", "/certifikater")
    fordeler = Datafordeler(
        certifikat_sti=os.path.join(certifikat_sti, "datafordeler.crt"),
        certifikat_nøglefil=os.path.join(certifikat_sti, "datafordeler.key"),
    )
    
    dwh_service = DWHService(
        server=dwh_creds.data["server"],
        username=dwh_creds.username,
        password=dwh_creds.password,
        database=dwh_creds.data["database"] 
    )
    
    tracker = Tracker(
        username=dwh_creds.username,
        password=dwh_creds.password
    )

    sbsys = SbsysClientManager(
        sbsys_credential.data["base_url"],
        sbsys_credential.data["token_url"],
        sbsys_credential.data["client_id"],
        sbsys_credential.data["client_secret"],
        sbsys_credential.username,
        sbsys_credential.password
    )
    
    sbsys_service = SbsysService(
        sbsys
    )
    
    sbsip.start_sbsip(
        brugernavn=sbsip_credential.username,
        adgangskode=sbsip_credential.password,
    )

    # Queue management
    if "--queue" in sys.argv:
        workqueue.clear_workqueue(WorkItemStatus.NEW)
        asyncio.run(populate_queue(workqueue))
        exit(0)

    # Process workqueue
    if not Path(args.word_template).is_file():
        raise FileNotFoundError(f"Word-skabelon ikke fundet: {args.word_template}")
    asyncio.run(process_workqueue(workqueue, args.word_template))
