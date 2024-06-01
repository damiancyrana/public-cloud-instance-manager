import tkinter as tk
from tkinter import messagebox, ttk
import threading
import time
import re
import pyperclip
from azure.identity import AzureCliCredential
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.resource import SubscriptionClient


class AzureVMManager:
    def __init__(self, root):
        self.root = root
        self.root.title("Public Cloud Instance Manager")
        self.root.geometry("900x900")
        self.root.configure(bg="#191a25")

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TButton", font=("Helvetica", 13), padding=10, background="#28293d", foreground="#fdfdfd", borderwidth=2, relief="raised", justify='center')
        style.map("TButton",
                  background=[('active', '#2596be')],
                  foreground=[('active', '#fdfdfd')],
                  bordercolor=[('active', '#40c1ac')],
                  relief=[('active', 'sunken')])
        
        style.configure("TLabel", font=("Helvetica", 13), background="#191a25", foreground="#fdfdfd")
        style.configure("TCombobox", font=("Helvetica", 13), background="#28293d", foreground="#fdfdfd", fieldbackground="#28293d")

        style.configure("TFrame", background="#191a25")
        style.configure("VM.TFrame", background="#28293d", borderwidth=2, relief="solid")

        self.subscription_label = ttk.Label(root, text="Wybierz Subskrypcję:", background="#191a25")
        self.subscription_label.grid(row=0, column=0, padx=10, pady=10, sticky="w")

        self.subscription_var = tk.StringVar(value="wszystko")
        self.subscription_menu = ttk.Combobox(root, textvariable=self.subscription_var, font=("Helvetica", 13), width=50)
        self.subscription_menu.grid(row=0, column=1, padx=10, pady=10, sticky="ew")

        self.refresh_button = ttk.Button(root, text="Pobierz VM", command=self.list_vms)
        self.refresh_button.grid(row=0, column=2, padx=10, pady=10, sticky="e")

        self.vm_frame = ttk.Frame(root)
        self.vm_frame.grid(row=1, column=0, columnspan=3, padx=10, pady=10, sticky="nsew")

        self.stats_frame = ttk.Frame(root, style="TFrame")
        self.stats_frame.grid(row=2, column=0, columnspan=3, padx=10, pady=10, sticky="ew")
        self.stats_label = ttk.Label(self.stats_frame, text="", style="TLabel")
        self.stats_label.grid(row=0, column=0, padx=10, pady=10)

        self.credential = AzureCliCredential()
        self.sub_client = SubscriptionClient(self.credential)
        self.list_subscriptions()

        self.author_label = ttk.Label(root, text="Autor: Damian Cyrana", background="#191a25", foreground="#fdfdfd", font=("Helvetica", 10))
        self.author_label.place(relx=1.0, rely=1.0, anchor='se', x=-10, y=-10)


    def list_subscriptions(self):
        self.subscriptions = [sub for sub in self.sub_client.subscriptions.list()]
        sub_names = ["wszystko"] + [sub.display_name for sub in self.subscriptions]
        self.subscription_menu['values'] = sub_names

    def list_vms(self):
        for widget in self.vm_frame.winfo_children():
            widget.destroy()

        selected_sub = self.subscription_var.get()
        if not selected_sub:
            messagebox.showwarning("Brak wybranej subskrypcji", "Wybierz subskrypcję z listy")
            return

        self.vms = []
        if selected_sub == "wszystko":
            for sub in self.subscriptions:
                compute_client = ComputeManagementClient(self.credential, sub.subscription_id)
                network_client = NetworkManagementClient(self.credential, sub.subscription_id)
                sub_vms = [vm for vm in compute_client.virtual_machines.list_all()]
                for vm in sub_vms:
                    vm.subscription_id = sub.subscription_id 
                    self.vms.append((vm, compute_client, network_client))
        else:
            sub_id = next(sub.subscription_id for sub in self.subscriptions if sub.display_name == selected_sub)
            compute_client = ComputeManagementClient(self.credential, sub_id)
            network_client = NetworkManagementClient(self.credential, sub_id)
            self.vms = [(vm, compute_client, network_client) for vm in compute_client.virtual_machines.list_all()]

        for idx, (vm, compute_client, network_client) in enumerate(self.vms):
            resource_group = self.extract_resource_group(vm.id)
            sub_name = next(sub.display_name for sub in self.subscriptions if sub.subscription_id == vm.subscription_id)
            vm_container = ttk.Frame(self.vm_frame, style="VM.TFrame", width=1000)
            vm_container.grid(row=idx, column=0, columnspan=7, padx=15, pady=15, sticky="ew")
            vm_container.grid_columnconfigure(0, weight=1)

            info_label = ttk.Label(vm_container, text=f"Sub: {sub_name}  |  RG: {resource_group}", background="#28293d", foreground="#fdfdfd", font=("Helvetica", 10))
            info_label.grid(row=0, column=0, columnspan=7, padx=10, pady=5, sticky="nsew")

            status_frame = tk.Canvas(vm_container, width=30, height=30, bg="#28293d", highlightthickness=0)
            status_frame.grid(row=1, column=0, padx=20, pady=20, sticky="w")
            self.update_vm_status(status_frame, vm, compute_client)

            vm_name = ttk.Label(vm_container, text=vm.name, background="#28293d", foreground="#fdfdfd")
            vm_name.grid(row=1, column=1, padx=10, pady=20, sticky="w")

            ip_address = self.get_public_ip(vm, network_client)
            ip_label = ttk.Label(vm_container, text=ip_address, cursor="hand2", background="#28293d", foreground="#fdfdfd")
            ip_label.grid(row=1, column=2, padx=10, pady=20, sticky="w")
            if ip_address:
                ip_label.bind("<Button-1>", lambda e, ip=ip_address: pyperclip.copy(ip))

            start_button = ttk.Button(vm_container, text="Włącz", command=lambda vm=vm, sf=status_frame, cc=compute_client: self.control_vm('start', vm, sf, cc))
            start_button.grid(row=1, column=3, padx=10, pady=20, sticky="e")

            stop_button = ttk.Button(vm_container, text="Wyłącz", command=lambda vm=vm, sf=status_frame, cc=compute_client: self.control_vm('deallocate', vm, sf, cc))
            stop_button.grid(row=1, column=4, padx=10, pady=20, sticky="e")

            restart_button = ttk.Button(vm_container, text="Restart", command=lambda vm=vm, sf=status_frame, cc=compute_client: self.control_vm('restart', vm, sf, cc))
            restart_button.grid(row=1, column=5, padx=10, pady=20, sticky="e")

            spacer_frame = ttk.Frame(vm_container, style="VM.TFrame")
            spacer_frame.grid(row=1, column=6, padx=10, pady=20)

        self.update_stats()
        self.update_all_vm_statuses()


    def get_public_ip(self, vm, network_client):
        try:
            for nic in vm.network_profile.network_interfaces:
                nic_name = nic.id.split('/')[-1]
                nic_info = network_client.network_interfaces.get(self.extract_resource_group(vm.id), nic_name)
                if nic_info.ip_configurations:
                    for ip_config in nic_info.ip_configurations:
                        if ip_config.public_ip_address:
                            public_ip_info = network_client.public_ip_addresses.get(self.extract_resource_group(vm.id), ip_config.public_ip_address.id.split('/')[-1])
                            return public_ip_info.ip_address
        except Exception as e:
            print(f"Error getting public IP: {e}")
        return "Brak IP"

    def control_vm(self, action, vm, status_frame, compute_client):
        resource_group = self.extract_resource_group(vm.id)
        if action == 'start':
            compute_client.virtual_machines.begin_start(resource_group, vm.name)
        elif action == 'deallocate':
            compute_client.virtual_machines.begin_deallocate(resource_group, vm.name)
        elif action == 'restart':
            compute_client.virtual_machines.begin_restart(resource_group, vm.name)
        self.root.after(1000, lambda: self.update_vm_status(status_frame, vm, compute_client))
        messagebox.showinfo("Operacja zakończona", f"Operacja {action} na maszynie {vm.name} została zainicjowana.")

    def extract_resource_group(self, vm_id):
        match = re.search(r'/resourceGroups/([^/]+)/', vm_id)
        return match.group(1) if match else None

    def schedule_task(self, action, vm, delay_seconds):
        threading.Timer(delay_seconds, self.control_vm, args=(action, vm)).start()
        self.schedules.append((action, vm.name, time.time() + delay_seconds))

    def update_stats(self):
        stats_text = f"Maszyny: {len(self.vms)}"
        self.stats_label.config(text=stats_text)

    def is_running(self, vm, compute_client):
        instance_view = compute_client.virtual_machines.instance_view(self.extract_resource_group(vm.id), vm.name)
        for status in instance_view.statuses:
            if (status.code == 'PowerState/running'):
                return True
        return False

    def update_vm_status(self, canvas, vm, compute_client):
        resource_group = self.extract_resource_group(vm.id)
        instance_view = compute_client.virtual_machines.instance_view(resource_group, vm.name)
        status_color = "red"
        for status in instance_view.statuses:
            if status.code == 'PowerState/running':
                status_color = "green"
            elif status.code == 'PowerState/deallocating' or status.code == 'PowerState/deallocated':
                status_color = "red"
            elif status.code == 'PowerState/restarting':
                status_color = "yellow"
        canvas.delete("all")
        canvas.create_oval(5, 5, 25, 25, fill=status_color)

    def update_all_vm_statuses(self):
        for idx, (vm, compute_client, network_client) in enumerate(self.vms):
            vm_container = self.vm_frame.grid_slaves(row=idx, column=0)[0]
            status_frame = vm_container.grid_slaves(row=1, column=0)[0]
            self.update_vm_status(status_frame, vm, compute_client)
        self.root.after(5000, self.update_all_vm_statuses)


if __name__ == "__main__":
    root = tk.Tk()
    root.grid_rowconfigure(1, weight=1)
    root.grid_columnconfigure(1, weight=1)
    app = AzureVMManager(root)
    root.mainloop()

    