import httpx
from proces.models import Borger
from automation_server_client import WorkItemError
from datafordeler import Datafordeler
from datetime import datetime
from pathlib import Path
import json
import sbsip 

class BrevService:
    @staticmethod
    def flet_og_send_brev(borger: Borger, fil_sti: str, fordeler: Datafordeler):
        
        brev_felter = {
            "PersonNavn": borger.navn,
            "Adresse": borger.adresse,
            "Postnr": str(borger.postnr),
            "ByNavn": borger.by,
            "Cpr": borger.cpr,
            "Dato": datetime.today().strftime("%d-%m-%Y"),
        }

        try:
            with open(
                fil_sti, "rb"
            ) as f:
                response = httpx.post(
                    "http://rpa-ats.odknet.dk:8331/render",
                    files={
                        "file": (fil_sti, f)
                    },
                    data={"fields": json.dumps(brev_felter)}     
                )
        except:
            raise RuntimeError("Teknisk fejl: Kunne ikke danne brev")
            
        pdf_path = Path("Danish Language Course.pdf")
        pdf_path.write_bytes(response.content)
        
        cpr_uden_bindestreg = borger.cpr.replace("-","")
        
        adresse, post_nr = fordeler.hent_adresse_til_sbsip(cpr_uden_bindestreg)

        try:
            sbsip.send_digital_post(
                cpr=cpr_uden_bindestreg,
                overskrift="Tilbud om danskundervisning",
                beskrivelse="Tilbud om danskundervisning",
                vedhæftet_fil=pdf_path,
                post_nr=post_nr,
                adresse=adresse,
                sbsys_skabelon_id="536"
            )
        except:
            pdf_path.unlink()
            raise RuntimeError("Teknisk fejl: Kunne ikke sende brev")
        
        pdf_path.unlink()
        
        