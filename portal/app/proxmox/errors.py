# Portal ожидал свою VM, но обнаружил под этим VMID другой ресурс
class ProviderResourceConflictError(RuntimeError):
    pass