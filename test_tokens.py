import asyncio
import os
import httpx

async def main():
    async with httpx.AsyncClient() as client:
        # Get OIDC
        res_meta = await client.get(
            "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity?audience=users_api",
            headers={"Metadata-Flavor": "Google"},
            timeout=2.0
        )
        if res_meta.status_code != 200:
            print("Failed OIDC")
            return
        oidc = res_meta.text
        
        # Get Short JWT
        res = await client.post("http://api.internal.zenika/api/users/service-account/login", json={"id_token": oidc})
        if res.status_code != 200:
            print("Failed short JWT", res.text)
            return
        short_jwt = res.json().get("access_token")
        
        # Get Service Token
        res2 = await client.post("http://api.internal.zenika/api/users/internal/service-token", headers={"Authorization": f"Bearer {short_jwt}"})
        if res2.status_code != 200:
            print("Failed service token", res2.text)
            return
        service_token = res2.json().get("access_token")
        print("Got service token!")
        
        # Test Competencies
        res_comp = await client.post("http://api.internal.zenika/api/competencies/bulk/cleanup-orphans", headers={"Authorization": f"Bearer {service_token}"})
        print("Competencies:", res_comp.status_code, res_comp.text)
        
        # Test Prompts
        res_prompt = await client.get("http://api.internal.zenika/api/prompts/cv_api.generate_taxonomy_tree_map", headers={"Authorization": f"Bearer {service_token}"})
        print("Prompts:", res_prompt.status_code, res_prompt.text)

asyncio.run(main())
