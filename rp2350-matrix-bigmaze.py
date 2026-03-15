# RP2350-Matrixの簡単なデモ
# 迷路を描き玉を転がす
# 迷路を大きくしてスクロールするようにした版
# 2026.3.16 by Tetsu=TaLow

from machine import I2C, Pin
import neopixel
import framebuf
import time
import random

# 迷路の1辺のサイズ　奇数である必要がある

MAZE_SIZE=25

# === ピン・定数設定 ===
I2C_SDA = 6
I2C_SCL = 7
WS2812_PIN = 25
LED_W = 8 # LEDの幅
LED_H = 8 # LEDの高さ
NUM_LEDS = LED_W * LED_H # LED総数

# 色の設定 (GRB形式)
COLOR_WALL = (0, 0, 5)   # 暗めの青 (まぶしさ防止)
COLOR_OUT = (0, 2, 0)    # 暗い赤
COLOR_PATH = (0, 0, 0)   # 黒 (消灯)
COLOR_PLAYER = (10, 0, 5)# エメラルドグリーン
COLOR_GOAL = (0, 5, 5)   # 紫 (ゴールの目印)
COLOR_MES = (10, 10, 0)  # 黄

# ゴール時のメッセージ
MES = " GOAL!"

# === QMI8658 センサードライバ ===
class QMI8658(object):
    def __init__(self,address=0X6B,i2c_num=1,i2c_sda=I2C_SDA,i2c_scl=I2C_SCL):
        self._address = address
        self._bus = I2C(id=i2c_num,scl=Pin(i2c_scl),sda=Pin(i2c_sda),freq=100_000) 
        if self.WhoAmI():
            self.Read_Revision()
        else:
            return None 
        self.Config_apply()

    def _read_byte(self,cmd):
        rec=self._bus.readfrom_mem(int(self._address),int(cmd),1)
        return rec[0]
    
    def _read_block(self, reg, length=1):
        rec=self._bus.readfrom_mem(int(self._address),int(reg),length)
        return rec
    
    def _write_byte(self,cmd,val):
        self._bus.writeto_mem(int(self._address),int(cmd),bytes([int(val)]))
        
    def WhoAmI(self):
        return (0x05) == self._read_byte(0x00)
    
    def Read_Revision(self):
        return self._read_byte(0x01)
    
    def Config_apply(self):
        self._write_byte(0x02,0x60)
        self._write_byte(0x03,0x23)
        self._write_byte(0x04,0x53)
        self._write_byte(0x05,0x00)
        self._write_byte(0x06,0x11)
        self._write_byte(0x07,0x00)
        self._write_byte(0x08,0x03)

    def Read_XYZ(self):
        xyz=[0,0,0,0,0,0]
        raw_xyz=self._read_block(0x35,12)  
        for i in range(6):
            xyz[i] = (raw_xyz[(i*2)+1]<<8)|(raw_xyz[i*2])
            if xyz[i] >= 32767: xyz[i] -= 65535
        
        acc_lsb_div=(1<<12)
        gyro_lsb_div = 64
        for i in range(3):
            xyz[i]=xyz[i]/acc_lsb_div
            xyz[i+3]=xyz[i+3]*1.0/gyro_lsb_div
        return xyz

# === 穴掘り法で迷路を作る ===
def generate_maze():
    # 盤面を壁(True)で埋める 外周は必ず壁にする
    # 奇数x奇数でないと作れないのでMAZE_SIZEは奇数である必要がある
    maze = [[True for _ in range(MAZE_SIZE)] for _ in range(MAZE_SIZE)]
    
    # 穴掘り法 (Depth-First Search)
    stack = [(1, 1)]    # スタート地点をスタックに積む
    maze[1][1] = False   # スタート地点は通路
    
    while stack:
        cx, cy = stack[-1] # Stak先頭の座標を取り出す
        # 上下左右の2マス先を表すリスト 
        dirs = [(0, -2), (0, 2), (-2, 0), (2, 0)]
        # dirsをランダムな順番でチェックするため並び替える
        for i in range(len(dirs) - 1, 0, -1):
            j = random.randint(0, i)
            dirs[i], dirs[j] = dirs[j], dirs[i]
            
        carved = False # 通路を掘ったか？
        for dx, dy in dirs: # 上下左右の方向をランダムに取り出す
            nx, ny = cx + dx, cy + dy # 現位置から2マス先の座標
            # 現在の座標の2つ先の座標が埋まっていたら
            if 0 <= nx < MAZE_SIZE  and 0 <= ny < MAZE_SIZE and maze[ny][nx]:
                # 間の壁と、その先のマスを通路(False)にする
                maze[cy + dy//2][cx + dx//2] = False
                maze[ny][nx] = False
                # 後でさらに掘り進むためにスタックに積む
                stack.append((nx, ny))
                carved = True # 通路を掘ったことを覚えておく
                break
                
        if not carved:
            stack.pop() # 通路を掘り進めなくなったら戻る
    return maze

# 大きくなるとわからなくなるのでヒント用にコンソールに迷路を描く
def draw_maze(maze):
    for y in range(MAZE_SIZE):
        s = ''.join('#' if v else ' ' for v in maze[y]) 
        print(s)                

# === メイン処理 ===

# ゴール表示用のフレームバッファを用意しておく
BUF_W = LED_W * len(MES)       # フレームバッファの幅
buf = bytearray(BUF_W * LED_H) # 文字ビットマップが入るバッファ
fb = framebuf.FrameBuffer(buf, BUF_W, LED_H, framebuf.MONO_HLSB) # 白黒のフレームバッファを作成
for i in range(len(MES)):
    fb.text(MES[i], i*LED_W, 0) # 文字を描く (ch, x, y)

# LED初期化
np = neopixel.NeoPixel(machine.Pin(WS2812_PIN), NUM_LEDS)

# センサー初期化
sensor = QMI8658()
print("ゲーム開始！基板を傾けてゴール(右下)を目指してください。")

while True:
    # 迷路の生成と初期化
    maze = generate_maze()
    draw_maze(maze) # ヒントとしてコンソールに迷路を表示
    px, py = 1, 1 # プレイヤーの初期座標 (左上)
    
    # 1ステージのゲームループ
    while True:
        # 1. 傾きセンサーの読み取り
        xyz = sensor.Read_XYZ()
        acc_y, acc_x = xyz[0], xyz[1]
        
        # 2. 移動判定 (0.15G以上の傾きで移動)
        THRESHOLD = 0.15
        new_x, new_y = px, py
        
        if acc_x < -THRESHOLD:  new_x -= 1
        elif acc_x > THRESHOLD: new_x += 1
        
        if acc_y > THRESHOLD:   new_y -= 1
        elif acc_y < -THRESHOLD: new_y += 1
        
        # 3. 衝突判定 (X軸とY軸を別々に判定)
        if 0 <= new_x < MAZE_SIZE and maze[py][new_x] == False:
            px = new_x
        if 0 <= new_y < MAZE_SIZE and maze[new_y][px] == False:
            py = new_y
        # 4. LEDの描画
        #    プレイヤーを中心にしてスクロールさせるように描く
        cx, cy = LED_W//2-1, LED_H//2-1 # 中心位置
        gx, gy = MAZE_SIZE-2, MAZE_SIZE-2 # ゴール位置
        for y in range(LED_H):
            for x in range(LED_W):
                idx = y * LED_H + x
                np[idx] = COLOR_PATH # 通路か迷路外
                dx, dy = x-cx+px, y-cy+py # 相対位置 
                if dx == px and dy == py:
                    np[idx] = COLOR_PLAYER #プレイヤー位置
                elif dx == gx and dy == gy: 
                    np[idx] = COLOR_GOAL # ゴール
                elif 0 <= dx < MAZE_SIZE and 0 <= dy < MAZE_SIZE:
                    if maze[dy][dx]: # Trueなら壁
                        np[idx] = COLOR_WALL # 壁
                    else:
                        np[idx] = COLOR_PATH # 通路
                else:
                    np[idx] = COLOR_OUT # 迷路外
        np.write()
        
        # 5. クリア判定
        if py == gy and px == gx:
            print("ゴール！次の迷路を生成します...")
            # クリア演出 (画面全体にメッセージをスクロール表示)
            for bx in range(BUF_W):
                for x in range(LED_W):
                    for y in range(LED_H):
                        idx = y * 8 + x
                        if fb.pixel(bx+x,y):
                            np[idx] = COLOR_MES
                        else:
                            np[idx] = (0,0,0)
                np.write()
                time.sleep(0.03) # スクロール速度
            break # 現在の迷路ループを抜けて新しい迷路を作る
            
        # 移動スピードの調整 (値を小さくすると速く動く)
        time.sleep(0.15)
