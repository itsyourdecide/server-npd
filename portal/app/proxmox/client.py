from typing import Any
from urllib.parse import quote

import httpx2


class ProxmoxClient:
    def __init__(
            self,
            api_url: str,
            token_id: str,
            token_secret: str,
            ca_file: str,
            timeout_seconds: float = 10,
    ) -> None:
        self._http = httpx2.AsyncClient(
            base_url=api_url.rstrip("/") + "/",
            headers={
                "Accept": "application/json",
                "Authorization": f"PVEAPIToken={token_id}={token_secret}"
           },

           verify=ca_file,
           timeout=timeout_seconds,
           follow_redirects=False,
           trust_env=False,
        )


    async def _request_data(
            self,
            method: str,
            path: str,
            *,
            data: dict[str, Any] | None = None,
            params: dict[str, Any] | None = None,
        ) -> Any:
            response = await self._http.request(
                method=method,
                url=path,
                data=data,
                params=params,
            )
            response.raise_for_status()
    
            body = response.json()
    
            if not isinstance(body, dict):
                raise RuntimeError("invalid Proxmox response body")  # noqa: TRY004
    
            if "data" not in body:
                raise RuntimeError("Proxmox response has no data field")
    
            return body["data"]

    
    async def get_version(self) -> dict[str, Any]:
        data = await self._request_data("GET", "version")
        if not isinstance(data, dict):
            raise ValueError(f"Invalid Proxmox version response: {data}")  # noqa: TRY004
        return data


    async def get_nodes(self) -> list[dict[str, Any]]:
        data = await self._request_data("GET", "nodes")
        if not isinstance(data, list):
            raise ValueError(f"Invalid Proxmox nodes response: {data}")  # noqa: TRY004
        return data


    async def aclose(self) -> None:
        await self._http.aclose()


    async def get_next_vmid(self) -> int:
        
        data = await self._request_data("GET", "cluster/nextid")

        if not isinstance(data, str):
            raise ValueError(f"Invalid Proxmox next VMID response: {data}")  # noqa: TRY004

        try:
            vmid = int(data)
        except ValueError as exc:
            raise ValueError(f"Invalid Proxmox next VMID value: {data}") from exc

        if vmid <= 0:
            raise ValueError(f"Invalid Proxmox next VMID value: {vmid}")

        return vmid


    async def clone_vm(
        self,
        *,
        source_node: str,
        target_node: str,
        template_vmid: int,
        new_vmid: int,
        name: str,
        storage: str,
        pool: str,
    ) -> str:

        path = f"nodes/{source_node}/qemu/{template_vmid}/clone"

        upid = await self._request_data(
            method="POST",
            path=path,
            data= {
                "newid": new_vmid,
                "name": name,
                "full": 1,
                "storage": storage,
                "pool": pool,
                "target": target_node,
            }
        )

        if not isinstance(upid, str) or not upid.startswith("UPID:"):
            raise ValueError(f"Invalid Proxmox clone request response: {upid}") 

        return upid

    async def get_task_status(
        self,
        *,
        node: str,
        upid: str,
    ) -> dict[str, Any]:

        encoded_upid = quote(upid, safe="")

        path = f"nodes/{node}/tasks/{encoded_upid}/status"

        data = await self._request_data(
            method="GET",
            path=path,
        )

        if not isinstance(data, dict):
            raise ValueError(f"Invalid Proxmox status request response: {data}")  # noqa: TRY004

        status = data.get("status")

        if not isinstance (status, str):
            raise ValueError(f"Invalid Proxmox status request response: {data}")  # noqa: TRY004

        return data

    async def configure_vm(
        self,
        *,
        node: str,
        vmid: int,
        vcpus: int,
        memory_mb: int,
        cloud_init_user: str,
        ipconfig0: str,
        nameserver: str,
        search_domain: str,
        ssh_public_key: str,
        tags: str,
    ) -> str | None:
        
        path = f"nodes/{node}/qemu/{vmid}/config"

        result = await self._request_data(
            method="POST",
            path=path,
            data={
                "cores": vcpus,
                "memory": memory_mb,
                "ciuser": cloud_init_user,
                "ipconfig0": ipconfig0,
                "nameserver": nameserver,
                "searchdomain": search_domain,
                "sshkeys": quote(ssh_public_key, safe=""),
                "protection": 0,
                "tags": tags,
            }
        )

        if result is None:
            return None

        if not isinstance(result, str) or not result.startswith("UPID:"):
            raise ValueError(f"Invalid Proxmox configure VM response: {result}")

        return result

    async def resize_vm_disk(
        self,
        *,
        node: str,
        vmid: int,
        disk: str,
        size_gb: int,
    ) -> str:

        if size_gb <= 0:
            raise ValueError("disk size must be positive")

        path = f"nodes/{node}/qemu/{vmid}/resize"

        upid = await self._request_data(
            method="PUT",
            path=path,
            data={
                "disk": disk,
                "size": f"{size_gb}G",
            },
        )

        if not isinstance(upid, str) or not upid.startswith("UPID:"):
            raise ValueError(f"Invalid Proxmox resize VM disk response: {upid}")

        return upid

    async def start_vm(
        self,
        *,
        node: str,
        vmid: int,
    ) -> str:
        
        path = f"nodes/{node}/qemu/{vmid}/status/start"

        upid = await self._request_data(
            method="POST",
            path=path,
        )

        if not isinstance(upid, str) or not upid.startswith("UPID:"):
            raise ValueError(f"Invalid Proxmox start VM response: {upid}")

        return upid

    async def shutdown_vm(
        self,
        *,
        node: str,
        vmid: int,
        timeout_seconds: int = 60,

    ) -> str:
        upid = await self._request_data(
        method="POST",
        path=f"nodes/{node}/qemu/{vmid}/status/shutdown",
        data={
            "timeout": timeout_seconds,
            "forceStop": 0,
        },
    )
        
        if not isinstance(upid, str) or not upid.startswith("UPID:"):
            raise ValueError(f"Invalid Proxmox shutdown VM response: {upid}")

        return upid

    async def stop_vm(
        self,
        *,
        node: str,
        vmid: int,
    ) -> str:
        
        path=f"nodes/{node}/qemu/{vmid}/status/stop"

        upid = await self._request_data(
            method="POST",
            path=path,
        )

        if not isinstance(upid, str) or not upid.startswith("UPID:"):
            raise ValueError(f"Invalid Proxmox stop VM response: {upid}")

        return upid

    async def delete_vm(
        self,
        *,
        node: str,
        vmid: int,
    ) -> str:
        upid = await self._request_data(
            method="DELETE",
            path=f"nodes/{node}/qemu/{vmid}",
            params={
                "purge": 1,
            },
        )

        if not isinstance(upid, str) or not upid.startswith("UPID:"):
            raise ValueError(f"Invalid Proxmox delete VM response: {upid}")

        return upid

    async def reboot_vm(
        self,
        *,
        node: str,
        vmid: int,
        timeout_seconds: int = 60,
    ) -> str:
        
        upid = await self._request_data(
            method="POST",
            path=f"nodes/{node}/qemu/{vmid}/status/reboot",
            data={
                "timeout": timeout_seconds,
            },
        )

        if not isinstance(upid, str) or not upid.startswith("UPID:"):
            raise ValueError(
                f"Invalid Proxmox reboot VM response: {upid}"
            )

        return upid


    async def list_vm_resources(self) -> list[dict[str, Any]]:

        resources= await self._request_data(
            "GET", 
            "cluster/resources", 
            params={"type": "vm"}
        )

        if not isinstance(resources, list):
            raise ValueError("Invalid Proxmox cluster/resources response")

        if not all(isinstance(resource, dict) for resource in resources):
            raise ValueError("Invalid VM resource in Proxmox response")

        return resources

    async def find_vm_resource(
        self,
        vmid: int,
    ) -> dict[str, Any] | None:
        if vmid <= 0:
            raise ValueError("VMID must be positive")

        resources = await self.list_vm_resources()
        matches: list[dict[str, Any]] = []

        for resource in resources:
            resource_vmid = resource.get("vmid")

            if not isinstance(resource_vmid, int):
                raise ValueError(f"Invalid VMID in Proxmox resource: {resource_vmid}")

            if resource_vmid == vmid:
                matches.append(resource)

        if len(matches) > 1:
            raise RuntimeError(f"Proxmox returned multiple resources with VMID {vmid}")

        if not matches:
            return None

        return matches[0]


    async def get_vm_current_status(
        self,
        *,
        node: str,
        vmid: int,
    ) -> dict[str, Any]:
        data = await self._request_data(
            method="GET",
            path=f"nodes/{node}/qemu/{vmid}/status/current",
        )

        if not isinstance(data, dict):
            raise ValueError(f"Invalid Proxmox VM status response: {data}")

        response_vmid = data.get("vmid")

        if response_vmid != vmid:
            raise ValueError("Proxmox returned status for another VM")

        return data