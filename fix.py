with open("cv_api/src/cvs/routers/taxonomy_router.py", "r") as f:
    lines = f.readlines()

new_lines = lines[:141]

new_lines.append("""@router.post("/recalculate_tree/batch/start", summary="Lance le processus batch asynchrone (Map)")
async def recalculate_tree_batch_start(request: Request, user: dict = Depends(verify_jwt)):
    from src.services.taxonomy_batch_service import TaxonomyBatchService
    auth_header = request.headers.get("Authorization")
    return await TaxonomyBatchService.start_batch(auth_header)


async def _generate_autonomous_service_token() -> str:
    from src.services.taxonomy_batch_service import TaxonomyBatchService
    return await TaxonomyBatchService.generate_autonomous_service_token()


@router.post("/recalculate_tree/batch/check", summary="Vérifie l'état du batch et avance la machine à états")
async def recalculate_tree_batch_check(request: Request, user: dict = Depends(verify_jwt)):
    from src.services.taxonomy_batch_service import TaxonomyBatchService
    auth_header = request.headers.get("Authorization")
    user_caller = user.get("sub", "scheduler")
    return await TaxonomyBatchService.check_batch(auth_header, user_caller)

""")

new_lines.extend(lines[835:])

with open("cv_api/src/cvs/routers/taxonomy_router.py", "w") as f:
    f.writelines(new_lines)
