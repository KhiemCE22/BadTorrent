import argparse
import os
import sys
import logging
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from PIL import Image, ImageTk 
import sqlite3
import database

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from client.client_node import ClientNode
from metainfo.metainfo import Metainfo
import logging_config
import threading

current_user_db = None

def login():
    global current_user_db, root
    root = tk.Tk()
    root.withdraw()  # Hide the root window
    class CustomDialog(simpledialog.Dialog):
        def body(self, master):
            tk.Label(master, text="Enter Username:").grid(row=0)
            self.username_entry = tk.Entry(master)
            self.username_entry.grid(row=0, column=1)
            return self.username_entry

        def apply(self):
            self.result = self.username_entry.get()

    dialog = CustomDialog(root)
    username = dialog.result
    if username:
        current_user_db = database.create_user_database(username)
        messagebox.showinfo("Success", f"Logged in as {username}")
        create_interface()


def download_torrent():
    global client, root
    
    # Hàm chọn file torrent (sẽ được gọi trong luồng chính)
    def select_torrent_file():
        torrent_file = filedialog.askopenfilename(title="Select Torrent File")
        if torrent_file:
            # Nếu chọn thành công, bắt đầu tải torrent trong một luồng con
            # Cập nhật cơ sở dữ liệu và giao diện sau khi tải xong
            database.add_download(current_user_db, torrent_file, "Downloading", 0.0)
            refresh_treeview()
            threading.Thread(target=download_torrent_file, args=(torrent_file,), daemon=True).start()
        else:
            messagebox.showwarning("Warning", "No torrent file selected")
    
    # Hàm tải torrent thực tế (sẽ chạy trong một luồng con)
    def download_torrent_file(torrent_file):
        try:
            # Thực hiện tải torrent
            client.download_torrent(torrent_file)
            root.after(0, refresh_treeview)  # Cập nhật giao diện trong luồng chính
            root.after(0, lambda: messagebox.showinfo("Success", "Torrent is downloading"))
        except Exception as e:
            root.after(0, lambda: messagebox.showerror("Error", f"Failed to download: {str(e)}"))
    
    # Gọi hàm chọn file torrent trong luồng chính
    select_torrent_file()

    # Giữ cửa sổ chính luôn hiển thị và không bị gián đoạn
    root.deiconify()

def download_magnet():
    magnet_link = simpledialog.askstring("Input", "Enter Magnet Link:")
    if magnet_link:
        client.download_magnet(magnet_link)
        database.add_download(current_user_db, magnet_link, "Downloading", 0.0)
        refresh_treeview()

def seed_torrent():
    global root  # Đảm bảo root được sử dụng toàn cục

    torrent_file = filedialog.askopenfilename(title="Select Torrent File")
    if not torrent_file:
        messagebox.showwarning("Warning", "No torrent file selected.")
        return

    # Hộp thoại tùy chỉnh để chọn chế độ seed
    mode_window = None  # Define mode_window before using it as nonlocal

    def choose_seed_mode():
        nonlocal mode_window
        mode_window = tk.Toplevel(root)
        mode_window.title("Select Seed Mode")
        mode_window.geometry("300x150")
        mode_window.transient(root)
        mode_window.grab_set()

        tk.Label(mode_window, text="Choose the type of seeding:", font=("Arial", 12)).pack(pady=10)

        def select_file():
            mode_result.set('file')
            mode_window.grab_release()
            mode_window.destroy()

        def select_folder():
            mode_result.set('folder')
            mode_window.grab_release()
            mode_window.destroy()

        tk.Button(mode_window, text="File", width=10, command=select_file).pack(pady=5)
        tk.Button(mode_window, text="Folder", width=10, command=select_folder).pack(pady=5)

    mode_result = tk.StringVar()
    choose_seed_mode()
    root.wait_window(mode_window)
    seed_mode = mode_result.get()
    if seed_mode == 'file':
        complete_path = filedialog.askopenfilename(title="Select Complete File")
    elif seed_mode == 'folder':
        complete_path = filedialog.askdirectory(title="Select Complete Folder")
    else:
        messagebox.showwarning("Warning", "No mode selected.")
        return

    if not complete_path:
        messagebox.showwarning("Warning", "No file or folder selected.")
        return

    def start_seeding():
        # Kiểm tra và bắt đầu seed
        try:
            if os.path.exists(complete_path):
                database.add_seed(current_user_db, torrent_file, "Seeding", 0.0)
                refresh_treeview()
                client.seed_torrent(torrent_file, complete_path)
                messagebox.showinfo("Success", "Seeding started")
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred: {str(e)}")

    # Chạy hàm start_seeding trong một luồng riêng biệt
    threading.Thread(target=start_seeding).start()



def show_status():
    client.show_status()
    downloads = database.get_downloads(current_user_db)
    seeds = database.get_seeds(current_user_db)
    print("Downloads:")
    for download in downloads:
        print(download)
    print("Seeds:")
    for seed in seeds:
        print(seed)

def stop_torrent():
    torrent_file = filedialog.askopenfilename(title="Select Torrent File")
    if torrent_file:
        client.stop_torrent(torrent_file)
        database.update_download(current_user_db, torrent_file, "Stopped", 0.0)
        refresh_treeview()


def create_torrent():
    input_path = filedialog.askopenfilename(title="Select File or Directory")
    tracker = simpledialog.askstring("Input", "Enter Tracker Address:")
    if input_path and tracker:
        output = filedialog.asksaveasfilename(defaultextension=".torrent", title="Save Torrent File As")
        piece_length = simpledialog.askinteger("Input", "Enter Piece Length (bytes):", initialvalue=524288)
        Metainfo.create_torrent_file(input_path, tracker, output, piece_length)
        messagebox.showinfo("Success", f"Torrent file created: {output}")

def on_closing():
    client.sign_out()
    root.destroy()
    sys.exit()

# Lưu trữ danh sách icon để tránh bị garbage collected
delete_icons = []

def create_interface():
    global root, tree, list_frame, delete_icon
    root = tk.Tk()
    root.title("Torrent Interface")
    root.geometry("800x600")

    # Tải hình ảnh icon xóa và giữ tham chiếu tại root
    if (os.path.exists("delete_icon.png")):
        delete_icon_image = Image.open("delete_icon.png").resize((20, 20 ), Image.Resampling.LANCZOS)
        delete_icon_image = delete_icon_image.convert("RGBA")
        background = Image.new("RGBA", delete_icon_image.size, (255, 255, 255, 255))  # Thêm nền trắng
        delete_icon_image = Image.alpha_composite(background, delete_icon_image)
        delete_icon = ImageTk.PhotoImage(delete_icon_image, master=root)
        delete_icons.append(delete_icon)
    else:
        print("Delete icon not found")
        delete_icon = None
    # Header (Add torrent & Create torrent buttons)
    header_frame = tk.Frame(root, bg="#333333", pady=10)
    header_frame.pack(fill=tk.X)

    add_torrent_button = tk.Button(header_frame, text="Download", bg="#3CB043", fg="white", padx=10, pady=5, command=download_torrent)
    add_torrent_button.pack(side=tk.RIGHT, padx=10)

    create_torrent_button = tk.Button(header_frame, text="Create torrent", bg="#3CB043", fg="white", padx=10, pady=5, command=create_torrent)
    create_torrent_button.pack(side=tk.RIGHT)

    seed_torrent_button = tk.Button(header_frame, text="Seed file", bg="#3CB043", fg="white", padx=10, pady=5, command=seed_torrent)
    seed_torrent_button.pack(side=tk.RIGHT, padx=10)

    # File List Area
    list_frame = tk.Frame(root, bg="#1e1e1e", padx=10, pady=10)
    list_frame.pack(fill=tk.BOTH, expand=True)


    tree = ttk.Treeview(list_frame, columns=("Name", "Status", "Progress", "Delete"), show="headings", height=15)
    tree.heading("Name", text="File Name")
    tree.heading("Status", text="Status")
    tree.heading("Progress", text="Progress")
    tree.heading("Delete", text="Delete")  # Cột Delete
    tree.column("Name", width=300)
    tree.column("Status", width=100)
    tree.column("Progress", width=100)
    tree.column("Delete", width=50, stretch=False)  # Cột Delete có chiều rộng cố định
    tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    # Scrollbar for the list
    scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=tree.yview)
    tree.configure(yscroll=scrollbar.set)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    root.protocol("WM_DELETE_WINDOW", on_closing)

    refresh_treeview()
    root.mainloop()


def refresh_treeview():
    """Cập nhật Treeview và thêm icon xóa bên cạnh mỗi dòng"""
    for widget in list_frame.winfo_children():
        if isinstance(widget, tk.Button):
            widget.destroy()  # Xóa tất cả nút xóa cũ

    for row in tree.get_children():
        tree.delete(row)

    downloads = database.get_downloads(current_user_db)
    seeds = database.get_seeds(current_user_db)
    y_position = 25  # Vị trí Y ban đầu cho các nút

    for download in downloads:
        item = tree.insert("", "end", values=(download[1], download[2], download[3], ""))
        add_delete_icon(item, download[1], y_position)
        y_position += 20
    for seed in seeds:
        item = tree.insert("", "end", values=(seed[1], seed[2], seed[3], ""))
        add_delete_icon(item, seed[1], y_position)
        y_position += 20

def add_delete_icon(item, file_name, y_position):
    """Thêm icon xóa vào bên cạnh mỗi dòng"""
    def on_delete():
        if messagebox.askyesno("Confirm", f"Are you sure you want to delete {file_name}?"):
            database.delete_download(current_user_db, file_name)
            status = tree.item(item, 'values')[1]
            if status == "Seeding":
                client.stop_torrent(file_name)
                database.delete_seed(current_user_db, file_name)
            else:
                database.delete_download(current_user_db, file_name)
            tree.delete(item)
            refresh_treeview()

    # Tạo nút với hình ảnh tùy chỉnh
    delete_button = tk.Button(
        list_frame,
        image=delete_icons[0],  # Sử dụng icon từ danh sách delete_icons
        bg="#1e1e1e",
        command=on_delete,
        borderwidth=0,
        highlightthickness=0,
        activebackground="#1e1e1e"
    )
    delete_button.place(x=720, y=y_position)  # Đặt nút bên cạnh Treeview



def main():
    global client
    client = ClientNode()

    parser = argparse.ArgumentParser(description="Torrent Client CLI")
    parser.add_argument('--gui', action='store_true', help='Launch GUI')
    subparsers = parser.add_subparsers(dest='command')

    # Command download
    download_parser = subparsers.add_parser('download')
    download_parser.add_argument('torrent_file', help='Path to the torrent file')
    download_parser.add_argument('--port', type=int, default=6881, help='Port to use for downloading')
    download_parser.add_argument('--download-dir', help='Directory to save the downloaded file')

    # Command download magnet
    download_magnet_parser = subparsers.add_parser('download_magnet')
    download_magnet_parser.add_argument('magnet_link', help='Magnet link to download the torrent')
    download_magnet_parser.add_argument('--download-dir', help='Directory to save the downloaded file')

    # Command seed
    seed_parser = subparsers.add_parser('seed')
    seed_parser.add_argument('torrent_file', help='Path to the torrent file')
    seed_parser.add_argument('complete_file', help='Path to the complete file to seed')
    seed_parser.add_argument('--port', type=int, default=6882, help='Port to use for seeding')

    # Command status
    status_parser = subparsers.add_parser('status')

    # Command peers
    peers_parser = subparsers.add_parser('peers')
    peers_parser.add_argument('torrent_file', help='Path to the torrent file')
    peers_parser.add_argument('--scrape', action='store_true', help='Scrape the tracker for peer information')
    peers_parser.add_argument('--get', action='store_true', help='Get the list of peers from the tracker')

    # Command stop
    stop_parser = subparsers.add_parser('stop')
    stop_parser.add_argument('torrent_file', help='Path to the torrent file')

    # Command remove
    remove_parser = subparsers.add_parser('remove')
    remove_parser.add_argument('torrent_file', help='Path to the torrent file')

    # Command create
    create_parser = subparsers.add_parser('create')
    create_parser.add_argument('input_path', help='Path to the file or directory to include in the torrent')
    create_parser.add_argument('--tracker', required=True, help='Tracker address')
    create_parser.add_argument('--output', default='output.torrent', help='Output torrent file name')
    create_parser.add_argument('--piece-length', type=int, default=524288, help='Piece length in bytes (default: 512 KB)')
    create_parser.add_argument('--magnet', action='store_true', help='Generate magnet link')

    # Parse initial arguments
    args = parser.parse_args()

    if args.gui:
        login()
    else:
        # If a command is provided, execute it
        if args.command:
            try:
                if args.command == 'download':
                    client.download_torrent(args.torrent_file, port=args.port, download_dir=args.download_dir)
                elif args.command == 'download_magnet':
                    client.download_magnet(args.magnet_link, download_dir=args.download_dir)
                elif args.command == 'seed':
                    client.seed_torrent(args.torrent_file, args.complete_file, port=args.port)
                elif args.command == 'status':
                    client.show_status()
                elif args.command == 'peers':
                    if args.scrape:
                        client.scrape_peers(args.torrent_file)
                    elif args.get:
                        client.show_peers(args.torrent_file)
                    else:
                        print("Unknown peers command")
                elif args.command == 'stop':
                    client.stop_torrent(args.torrent_file)
                elif args.command == 'remove':
                    client.remove_torrent(args.torrent_file)
                elif args.command == 'create':
                    Metainfo.create_torrent_file(args.input_path, args.tracker, args.output, args.piece_length)
                    if args.magnet:
                        storage = Metainfo(args.output)
                        magnet_link = storage.create_magnet_link()
                        print(f"Magnet link: {magnet_link}")
                else:
                    print("Unknown command")
            except Exception as e:
                print(f"Error executing command: {e}")

        # Enter interactive mode
        try:
            while True:
                command = input(">>> ").split()
                if not command:
                    continue
                if command[0] == 'exit':
                    break
                try:
                    args = parser.parse_args(command)
                except SystemExit:
                    print("Invalid command. Please try again.")
                    continue

                if args.command == 'download':
                    client.download_torrent(args.torrent_file, port=args.port, download_dir=args.download_dir)
                elif args.command == 'download_magnet':
                    client.download_magnet(args.magnet_link, download_dir=args.download_dir)
                elif args.command == 'seed':
                    client.seed_torrent(args.torrent_file, args.complete_file, port=args.port)
                elif args.command == 'status':
                    client.show_status()
                elif args.command == 'peers':
                    if args.scrape:
                        client.scrape_peers(args.torrent_file)
                    elif args.get:
                        client.show_peers(args.torrent_file)
                    else:
                        print("Unknown peers command")
                elif args.command == 'stop':
                    client.stop_torrent(args.torrent_file)
                elif args.command == 'remove':
                    client.remove_torrent(args.torrent_file)
                elif args.command == 'create':
                    Metainfo.create_torrent_file(args.input_path, args.tracker, args.output, args.piece_length)
                    if args.magnet:
                        storage = Metainfo(args.output)
                        magnet_link = storage.create_magnet_link()
                        print(f"Magnet link: {magnet_link}")
                else:
                    print("Unknown command")
        finally:
            # Sign out when exiting if an event was announced
            client.sign_out()

if __name__ == '__main__':
    main()