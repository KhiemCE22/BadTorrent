import argparse
import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk, Toplevel
from PIL import Image, ImageTk 
from urllib.parse import urlparse, parse_qs
import pyperclip  # Thư viện để sao chép văn bản vào clipboard
import sqlite3
import database

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from client.client_node import ClientNode
from metainfo.metainfo import Metainfo
import threading

current_user_db = None
running = True
download_threads = {}
#######################################GUI############################################
def parse_magnet_link(magnet_link):
    """Parse magnet link để lấy info_hash và name."""
    try:
        # Phân tích cú pháp magnet link
        parsed = urlparse(magnet_link)
        if parsed.scheme != "magnet":
            raise ValueError("Invalid magnet link")
        
        # Lấy các tham số từ magnet link
        params = parse_qs(parsed.query)
        info_hash = params.get("xt", [None])[0]  # Lấy `xt` (info_hash)
        if info_hash and info_hash.startswith("urn:btih:"):
            info_hash = info_hash.split("urn:btih:")[1]

        name = params.get("dn", [None])[0]  # Lấy `dn` (name)

        return {"info_hash": info_hash, "name": name}
    except Exception as e:
        raise ValueError(f"Error parsing magnet link: {e}")

def login():
    global current_user_db, root, background_image
    root = tk.Tk()
    root.title("Login")
    root.geometry("400x600")
    root.resizable(False, False)
    # Hình nền
    background_image = None
    if os.path.exists("resource/hcmut.png"):
        img = Image.open("resource/hcmut.png").resize((400, 300), Image.Resampling.LANCZOS)
        background_image = ImageTk.PhotoImage(img)
        logo_label = tk.Label(root, image=background_image)
        logo_label.pack(fill="x", pady=10)  # Đặt logo phía trên cùng

    # Khung đăng nhập
    login_frame = tk.Frame(root, bg="#f0f0f0", bd=5)
    login_frame.pack(pady=20, padx=20, fill="x", expand=False)  # Đặt khung đăng nhập phía dưới

    # Tiêu đề
    tk.Label(
        login_frame, text="Login",
        font=("Helvetica", 16, "bold"), bg="#f0f0f0"
    ).pack(pady=10)

    # Nhập username
    tk.Label(
        login_frame, text="Username:",
        font=("Helvetica", 12), bg="#f0f0f0"
    ).pack(anchor="w", padx=10)

    username_entry = ttk.Entry(login_frame, font=("Helvetica", 12))
    username_entry.pack(pady=5, padx=10, fill="x")

    # Nút đăng nhập
    def on_login():
        username = username_entry.get()
        print("Login")
        if username:
            global current_user_db
            current_user_db = database.create_user_database(username)
            restore_previous_session()
            root.destroy()  # Đóng cửa sổ đăng nhập
            create_interface()
        else:
            messagebox.showwarning("Warning", "Please enter a username!")

    login_button = ttk.Button(login_frame, text="Login", command=on_login)
    login_button.pack(pady=10)

    # Định nghĩa khi đóng
    def on_closing():
        global running
        running = False
        root.destroy()
        os._exit(0)

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()


def add_placeholder(entry, placeholder_text):
    """Thêm placeholder vào ô nhập liệu."""
    entry.insert(0, placeholder_text)
    entry.config(fg="grey")  # Đổi màu chữ để phân biệt placeholder

    def on_focus_in(event):
        if entry.get() == placeholder_text:
            entry.delete(0, tk.END)
            entry.config(fg="black")  # Đổi màu chữ lại bình thường

    def on_focus_out(event):
        if entry.get() == "":
            entry.insert(0, placeholder_text)
            entry.config(fg="grey")

    entry.bind("<FocusIn>", on_focus_in)
    entry.bind("<FocusOut>", on_focus_out)

def restore_previous_session():
    """Khôi phục phiên làm việc trước."""
    print("Restoring previous session...")
    downloads = database.get_downloads(current_user_db)
    seeds = database.get_seeds(current_user_db)
    for download in downloads:
        if download[2] == "Downloading":
            download_threads[download[6]] = True
            threading.Thread(target=handle_torrent_download, args=(download[5], download[6], download[7]), daemon=True).start()
    for seed in seeds:
        print(f"Seed tuple: {seed}")  # In ra nội dung của tuple seed để kiểm tra
        if seed[2] == "Seeding":
            threading.Thread(target=seed_torrent, args=("restore",seed[6], seed[4]), daemon=True).start()

def download_interface():
    share_window = Toplevel(root)
    share_window.title("Torrent Download Interface")
    share_window.geometry("500x400")

    # Tiêu đề chính
    tk.Label(
        share_window, text="Download Torrent", font=("Arial", 16, "bold"), pady=10
    ).pack()

    # Phần trên: Download bằng file torrent
    frame_file = tk.LabelFrame(share_window, text="Via Torrent File", padx=10, pady=10, font=("Arial", 12, "bold"))
    frame_file.pack(fill=tk.X, padx=20, pady=10)

    torrent_path_entry = tk.Entry(frame_file, width=40, font=("Arial", 10))
    torrent_path_entry.config(state="readonly")
    torrent_path_entry.grid(row=0, column=0, padx=(0, 5), pady=5, sticky="w")
    tk.Button(
        frame_file, text="Browse", bg="#3CB043", fg="white", command=lambda: browse_file(torrent_path_entry)
    ).grid(row=0, column=1, padx=5)

    # Phần dưới: Download bằng magnet link
    frame_magnet = tk.LabelFrame(share_window, text="Via Magnet Link", padx=10, pady=10, font=("Arial", 12, "bold"))
    frame_magnet.pack(fill=tk.X, padx=20, pady=10)

    magnet_entry = tk.Entry(frame_magnet, width=40, font=("Arial", 10))
    placeholder_text = "Paste your magnet link here"
    add_placeholder(magnet_entry, placeholder_text)
    magnet_entry.grid(row=0, column=0, padx=(0, 5), pady=5, sticky="w")

    # Nơi lưu file sau khi tải xuống
    frame_location = tk.LabelFrame(share_window, text="Download Location", padx=10, pady=10, font=("Arial", 12, "bold"))
    frame_location.pack(fill=tk.X, padx=20, pady=10)

    location_entry = tk.Entry(frame_location, width=40, font=("Arial", 10))
    location_entry.config(state="readonly")
    location_entry.grid(row=0, column=0, padx=(0, 5), pady=5, sticky="w")
    tk.Button(
        frame_location, text="Browse", bg="#3CB043", fg="white", command=lambda: browse_directory(location_entry)
    ).grid(row=0, column=1, padx=5)

    # Chức năng browse
    def browse_file(entry):
        file_path = filedialog.askopenfilename(title="Select Torrent File")
        if file_path:
            entry.config(state="normal")
            entry.delete(0, tk.END)
            entry.insert(0, file_path)
            entry.config(state="readonly")

    def browse_directory(entry):
        directory_path = filedialog.askdirectory(title="Select Download Location")
        if directory_path:
            entry.config(state="normal")
            entry.delete(0, tk.END)
            entry.insert(0, directory_path)
            entry.config(state="readonly")

    # Nút tải xuống
    download_button = tk.Button(
        share_window, text="Download", bg="#0078D7", fg="white", font=("Arial", 12, "bold"), padx=10, pady=5
    )
    download_button.pack(pady=20)

    # Chức năng tải và đóng cửa sổ
    def close_window():
        share_window.destroy()

    def download_and_close():
        if magnet_entry.get() and magnet_entry.get() != placeholder_text and location_entry.get():
            download_magnet(magnet_entry.get(), location_entry.get())
            close_window()
        elif torrent_path_entry.get() and location_entry.get():
            download_torrent(torrent_path_entry.get(), location_entry.get())
            close_window()
        else:
            messagebox.showwarning("Warning", "Please select a download location and torrent file/magnet link")

    download_button.config(command=download_and_close)

    # Đặt cửa sổ con thành modal
    share_window.transient(root)
    share_window.grab_set()
    root.wait_window(share_window)



def download_torrent(torrent_file, download_dir):
    if torrent_file:
        # Xử lý tải xuống trong luồng riêng
        meta = Metainfo(torrent_file)
        name = meta.info[b'name'].decode('utf-8')
        magnet = meta.create_magnet_link()
        info_hash = meta.get_info_hash()
        database.add_download(current_user_db, name, "Downloading", 0.0, magnet, torrent_file, download_dir, info_hash)
        refresh_treeview()
        download_threads[info_hash] = True
        threading.Thread(target=handle_torrent_download, args=(torrent_file, info_hash, download_dir), daemon=True).start()
    else:
        messagebox.showwarning("Warning", "No torrent file selected")

def handle_torrent_download(torrent_file, info_hash, download_dir):
    """Hàm tải file torrent."""
    try:
        while running and download_threads.get(info_hash, True):
            success = client.download_torrent(torrent_file, download_dir=download_dir)
            if success:
                root.after(0, lambda: database.update_download(current_user_db, info_hash, "Completed", 100.0))
                root.after(0, refresh_treeview)
                root.after(0, lambda: messagebox.showinfo("Success", "Torrent download completed"))
                break
            if not download_threads.get(info_hash, True) or info_hash not in download_threads:
                break
    except Exception as e:
        root.after(0, lambda: messagebox.showerror("Error", f"Failed to download: {str(e)}"))

def download_magnet(magnet_link, download_dir):
    """Tải bằng link magnet."""
    if not magnet_link:
        messagebox.showwarning("Warning", "Magnet link cannot be empty.")
        return

    try:
        print(magnet_link)
        parsed = parse_magnet_link(magnet_link)
        database.add_download(current_user_db, parsed["name"], "Downloading", 0.0, magnet_link, None, download_dir, parsed["info_hash"])
        download_threads[parsed["info_hash"]] = True
        threading.Thread(target=handle_magnet_download, args=(magnet_link, parsed["info_hash"], download_dir), daemon=True).start()
    except Exception as e:
        messagebox.showerror("Error", f"Failed to download magnet: {str(e)}")
        
def handle_magnet_download(magnet_link,info_hash, download_dir):
    """Xử lý tải magnet trong luồng riêng."""
    try:
        while running and download_threads.get(info_hash, True):
            success = client.download_magnet(magnet_link, download_dir=download_dir)
            if success:
                root.after(0, lambda: database.update_download(current_user_db, info_hash, "Completed", 100.0))
                root.after(0, refresh_treeview)
                root.after(0, lambda: messagebox.showinfo("Success", "Magnet download completed"))
                break
            if not download_threads.get(info_hash, True) or info_hash not in download_threads:
                break
    except Exception as e:
        root.after(0, lambda: messagebox.showerror("Error", f"Failed to download: {str(e)}"))

def seed_torrent(mode = None, complete_path = None, torrent_file = None):
    global root  # Đảm bảo root được sử dụng toàn cục
    if (mode != "restore"):
        torrent_file = filedialog.askopenfilename(title="Select Torrent File")
        if not torrent_file:
            messagebox.showwarning("Warning", "No torrent file selected.")
            return
        meta = Metainfo(torrent_file)
        magnet = meta.create_magnet_link()
        name = meta.info[b'name'].decode('utf-8')
        info_hash = meta.get_info_hash()
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
        database.add_seed(current_user_db, name, "Seeding", magnet, torrent_file, complete_path, info_hash)
        root.after(0, refresh_treeview)  # Cập nhật giao diện trong luồng chính

    def start_seeding():
            # Kiểm tra và bắt đầu seed
            try:
                while running:
                    if complete_path and os.path.exists(complete_path):
                        client.seed_torrent(torrent_file, complete_path)
                        root.after(0, lambda: messagebox.showinfo("Success", "Seeding started"))
                        break
            except Exception as e:
                root.after(0, lambda e=e: messagebox.showerror("Error", f"An error occurred: {str(e)}"))
    # Chạy hàm start_seeding trong một luồng riêng biệt
    threading.Thread(target=start_seeding).start()



def create_torrent():
    input_path = filedialog.askopenfilename(title="Select File or Directory")
    tracker = simpledialog.askstring("Input", "Enter Tracker Address:")
    if input_path and tracker:
        output = filedialog.asksaveasfilename(defaultextension=".torrent", title="Save Torrent File As")
        piece_length = simpledialog.askinteger("Input", "Enter Piece Length (bytes):", initialvalue=524288)
        Metainfo.create_torrent_file(input_path, tracker, output, piece_length)
        messagebox.showinfo("Success", f"Torrent file created: {output}")

def on_closing():
    global running
    running = False
    client.sign_out()
    root.destroy()
    sys.exit()

# Lưu trữ danh sách icon để tránh bị garbage collected
icons = []

def update_button_positions():
    """Cập nhật vị trí của các nút delete và share khi thay đổi kích thước cửa sổ"""
    for widget in list_frame.winfo_children():
        if isinstance(widget, tk.Button):
            # Kiểm tra nút và điều chỉnh vị trí
            if widget.cget("image") == str(icons[0]):  # Nút delete
                widget.place(x=root.winfo_width() - 70)
            elif widget.cget("image") == str(icons[1]):  # Nút share
                widget.place(x=root.winfo_width() - 120)


def create_interface():
    global root, tree, list_frame, delete_icon
    root = tk.Tk()
    root.title("Torrent Interface")
    root.geometry("800x600")

    def load_icon(icon_path, error_message):
        if os.path.exists(icon_path):
            icon_image = Image.open(icon_path).resize((20, 20), Image.Resampling.LANCZOS)
            icon_image = icon_image.convert("RGBA")
            background = Image.new("RGBA", icon_image.size, (255, 255, 255, 255))
            icon_image = Image.alpha_composite(background, icon_image)
            icon = ImageTk.PhotoImage(icon_image, master=root)
            icons.append(icon)
        else:
            print(error_message)

    # Load icons
    load_icon("resource/delete_icon.png", "Delete icon not found")
    load_icon("resource/share_icon.png", "Share icon not found")
    load_icon("resource/copy_icon.png", "Copy icon not found")

    # Header
    header_frame = tk.Frame(root, bg="#333333", pady=10)
    header_frame.pack(fill=tk.X)

    # Title label
    title_label = tk.Label(header_frame, text="Torrent Manager", bg="#333333", fg="white", font=("Arial", 16, "bold"))
    title_label.pack(side=tk.LEFT, padx=10)

    # Button Area
    button_frame = tk.Frame(header_frame, bg="#333333")
    button_frame.pack(side=tk.RIGHT, padx=10)

    # Arrange buttons in a grid
    download_button = tk.Button(button_frame, text="Download", bg="#3CB043", fg="white", padx=10, pady=5, command=download_interface)
    create_torrent_button = tk.Button(button_frame, text="Create torrent", bg="#3CB043", fg="white", padx=10, pady=5, command=create_torrent)
    seed_button = tk.Button(button_frame, text="Start seeding", bg="#3CB043", fg="white", padx=10, pady=5, command=seed_torrent)

    download_button.grid(row=0, column=0, padx=5, pady=5)
    create_torrent_button.grid(row=0, column=1, padx=5, pady=5)
    seed_button.grid(row=0, column=2, padx=5, pady=5)

    # Separator
    separator = ttk.Separator(root, orient=tk.HORIZONTAL)
    separator.pack(fill=tk.X, pady=5)

    # File List Area
    list_frame = tk.Frame(root, bg="#1e1e1e", padx=10, pady=10)
    list_frame.pack(fill=tk.BOTH, expand=True)

    tree = ttk.Treeview(list_frame, columns=("Name", "Status", "Progress", "Share", "Delete"), show="headings", height=15)
    tree.heading("Name", text="File Name")
    tree.heading("Status", text="Status")
    tree.heading("Progress", text="Progress")
    tree.heading("Share", text="", anchor="center")
    tree.heading("Delete", text="", anchor="center")

    tree.column("Name", width=300)
    tree.column("Status", width=100, anchor="center")
    tree.column("Progress", width=100, anchor="center")
    tree.column("Share", width=50, stretch=False)
    tree.column("Delete", width=50, stretch=False)
    tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    # Scrollbar for the list
    scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=tree.yview)
    tree.configure(yscroll=scrollbar.set)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    root.protocol("WM_DELETE_WINDOW", on_closing)

    refresh_treeview()
    root.bind("<Configure>", lambda event: update_button_positions())
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
        item = tree.insert("", "end", values=(download[1], download[2], download[3], "", ""))
        add_share_icon(item, download[1], y_position, download[6])
        add_delete_icon(item, download[1], y_position, download[6], file_torrent=download[5])
        y_position += 20
    for seed in seeds:
        progress = "-/-"
        item = tree.insert("", "end", values=(seed[1], seed[2], progress, "", ""))
        add_share_icon(item, seed[1], y_position, seed[5])
        add_delete_icon(item, seed[1], y_position, seed[5], file_torrent=seed[4])   
        y_position += 20

def add_delete_icon(item, file_name, y_position, info_hash, file_torrent):
    """Thêm icon xóa vào bên cạnh mỗi dòng"""
    def on_delete():
        print("file_torrent", file_torrent)
        if messagebox.askyesno("Confirm", f"Are you sure you want to delete {file_name}?"):
            status = tree.item(item, 'values')[1]
            if status == "Seeding":
                client.stop_torrent(file_torrent)
                database.delete_seed(current_user_db, info_hash)
            else:
                database.delete_download(current_user_db, info_hash)
                download_threads[info_hash] = False
                del download_threads[info_hash]
            tree.delete(item)
            refresh_treeview()
    # Tạo nút với hình ảnh tùy chỉnh
    delete_button = tk.Button(
        list_frame,
        image=icons[0],  # Sử dụng icon từ danh sách delete_icons
        bg="#1e1e1e",
        command=on_delete,
        borderwidth=0,
        highlightthickness=0,
        activebackground="#1e1e1e"
    )
    delete_button.place(x=root.winfo_width() - 70, y=y_position)  # Đặt nút bên cạnh Treeview




def add_share_icon(item, file_name, y_position, info_hash):
    """Thêm icon chia sẻ vào bên cạnh mỗi dòng"""
    def on_share():
        # Lấy magnet link từ database
        magnet_link = database.get_magnet(current_user_db, info_hash)
        if not magnet_link:
            messagebox.showwarning("Warning", f"No magnet link found for {file_name}")
            return
        
        # Tạo một cửa sổ con để hiển thị magnet link và nút copy
        share_window = Toplevel(root)
        share_window.title("Share Magnet Link")
        share_window.geometry("500x100")
        share_window.resizable(False, False)

        # Magnet link label
        tk.Label(share_window, text="Magnet Link:", font=("Arial", 12, "bold")).pack(anchor="w", padx=10, pady=5)

        # Frame for magnet link entry and copy button
        magnet_frame = tk.Frame(share_window)
        magnet_frame.pack(padx=10, pady=5)

        # Magnet link entry box
        magnet_entry = tk.Entry(magnet_frame, font=("Arial", 10), bd=2, relief="solid", width=50)
        magnet_entry.insert(0, magnet_link)  # Hiển thị magnet link
        magnet_entry.config(state="readonly")  # Không cho phép chỉnh sửa
        magnet_entry.pack(side=tk.LEFT)

        # Copy function
        def copy_to_clipboard():
            pyperclip.copy(magnet_link)
            messagebox.showinfo("Copied", "Magnet link copied to clipboard!")

        # Copy button          
        tk.Button(magnet_frame, image=icons[2], command=copy_to_clipboard, borderwidth=0).pack(side=tk.LEFT, padx=5)

    # Tạo nút Share với hình ảnh tùy chỉnh
    share_button = tk.Button(
        list_frame,
        image=icons[1],  # Sử dụng icon từ danh sách share_icons
        bg="#1e1e1e",
        command=on_share,
        borderwidth=0,
        highlightthickness=0,
        activebackground="#1e1e1e"
    )
    
    share_button.place(x=root.winfo_width() - 120, y=y_position)  # Đặt nút bên cạnh Treeview

#######################################CLI############################################

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