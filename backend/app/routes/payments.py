"""Paid evidence purchases (x402 on Solana devnet) and their receipts."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ..core import Services, current_principal, get_services, require_mission_access
from ..payments.x402_exchange import payments_for_mission, purchase_supplier_dossier

router = APIRouter()


@router.post("/v1/missions/{mission_id}/suppliers/{supplier_id}/premium-dossier", status_code=status.HTTP_201_CREATED)
async def buy_premium_dossier(mission_id: str, supplier_id: str, principal: dict = Depends(current_principal),
                              services: Services = Depends(get_services)) -> dict:
    """Buy a signed public-records dossier through HTTP 402. Bounded by the org's devnet data budget."""

    mission, _ = await require_mission_access(mission_id, principal, services)
    if principal["role"] not in {"coordinator", "agent"}:
        raise HTTPException(status_code=403, detail="Only coordinators or the org agent can buy evidence")
    if principal["role"] == "agent" and principal.get("sender") not in services.settings.agent_privileged_senders:
        raise HTTPException(status_code=403, detail="Paid evidence purchases are limited to authorized agent conversations")
    quotes = await services.store.find("quotes", mission_id=mission_id, supplier_id=supplier_id)
    supplier = await services.store.get("suppliers", supplier_id)
    if not quotes or not supplier:
        raise HTTPException(status_code=404, detail="Supplier is not participating in this mission")
    return await purchase_supplier_dossier(services, mission, supplier, principal)


@router.get("/v1/missions/{mission_id}/payments")
async def list_payments(mission_id: str, principal: dict = Depends(current_principal),
                        services: Services = Depends(get_services)) -> list:
    await require_mission_access(mission_id, principal, services)
    return await payments_for_mission(services, mission_id)
