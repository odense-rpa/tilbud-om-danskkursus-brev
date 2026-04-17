import asyncio
import logging
import sys

from automation_server_client import AutomationServer, Workqueue, WorkItemError, Credential, WorkItemStatus
from proces.dwh_service import DWHService
from proces.models import Borger

proces_navn = "Tilbud om danskkursusbrev"
dwh_service: DWHService

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
        )
        workqueue.add_item(borger_obj.model_dump(), borger_obj.cpr)


async def process_workqueue(workqueue: Workqueue):
    logger = logging.getLogger(__name__)

    logger.info("Hello from process workqueue!")

    for item in workqueue:
        with item:
            data = item.data  # Item data deserialized from json as dict
 
            try:
                # Process the item here
                pass
            except WorkItemError as e:
                # A WorkItemError represents a soft error that indicates the item should be passed to manual processing or a business logic fault
                logger.error(f"Error processing item: {data}. Error: {e}")
                item.fail(str(e))


if __name__ == "__main__":
    ats = AutomationServer.from_environment()
    workqueue = ats.workqueue()

    # Initialize external systems for automation here..
    dwh_creds = Credential.get_credential("Odense SQL Server")
    
    dwh_service = DWHService(
        server=dwh_creds.data["server"],
        username=dwh_creds.username,
        password=dwh_creds.password,
        database=dwh_creds.data["database"] 
    )

    # Queue management
    if "--queue" in sys.argv:
        workqueue.clear_workqueue(WorkItemStatus.NEW)
        asyncio.run(populate_queue(workqueue))
        exit(0)

    # Process workqueue
    asyncio.run(process_workqueue(workqueue))
