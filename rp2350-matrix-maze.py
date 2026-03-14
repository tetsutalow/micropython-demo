# RP2350-Matrixの簡単なデモ
# 迷路を描き玉を転がす
# 2026.3.12 by Tetsu=TaLow

from machine import I2C, Pin
import neopixel
import framebuf
import time
import random

# === ピン・定数設定 ===
I2C_SDA = 6
I2C_SCL = 7
WS2812_PIN = 25
LED_W = 8 # LEDの幅
LED_H = 8 # LEDの高さ
NUM_LEDS = LED_W * LED_H # LED総数

# 色の設定 (GRB形式)
COLOR_WALL = (0, 0, 5)   # 暗めの青 (まぶしさ防止)
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
    # 盤面を壁(1)で埋める
    # 奇数x奇数でないと作れない　LEDは8x8なので1つ多く作る
    maze = [[1 for _ in range(LED_H+1)] for _ in range(LED_W+1)]
    
    # 穴掘り法 (Depth-First Search)
    stack = [(0, 0)] # スタート地点をスタックに積む
    maze[0][0] = 0   # スタート地点は通路
    
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
            if 0 <= nx <= LED_W and 0 <= ny <= LED_H and maze[ny][nx] == 1:
                # 間の壁と、その先のマスを通路(0)にする
                maze[cy + dy//2][cx + dx//2] = 0
                maze[ny][nx] = 0
                # 後でさらに掘り進むためにスタックに積む
                # ただしLEDアレイの範囲外になった時は積まない
                # （つまり袋小路にする そうしないと見えない通路が出来てしまう）
                if ny < LED_H and nx < LED_W:
                    stack.append((nx, ny))
                carved = True # 通路を掘ったことを覚えておく
                break
                
        if not carved:
            stack.pop() # 通路を掘り進めなくなったら戻る
    
    maze[LED_W-1][LED_W-1]=0 # ゴールは開ける
    return maze

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
    px, py = 0, 0 # プレイヤーの初期座標 (左上)
    
    # 1ステージのゲームループ
    while True:
        # 1. 傾きセンサーの読み取り
        xyz = sensor.Read_XYZ()
        print("xyz=",xyz)
        acc_y, acc_x = xyz[0], xyz[1]
        
        # 2. 移動判定 (0.15G以上の傾きで移動)
        THRESHOLD = 0.15
        new_x, new_y = px, py
        
        if acc_x < -THRESHOLD:  new_x -= 1
        elif acc_x > THRESHOLD: new_x += 1
        
        if acc_y > THRESHOLD:   new_y -= 1
        elif acc_y < -THRESHOLD: new_y += 1
        
        # 3. 衝突判定 (X軸とY軸を別々に判定)
        if 0 <= new_x < 8 and maze[py][new_x] == 0:
            px = new_x
        if 0 <= new_y < 8 and maze[new_y][px] == 0:
            py = new_y
            
        # 4. LEDの描画
        for y in range(LED_H):
            for x in range(LED_W):
                idx = y * LED_H + x
                if x == px and y == py:
                    np[idx] = COLOR_PLAYER
                elif x == LED_W-1 and y == LED_H-1:
                    np[idx] = COLOR_GOAL
                elif maze[y][x] == 1:
                    np[idx] = COLOR_WALL
                else:
                    np[idx] = COLOR_PATH
        np.write()
        
        # 5. クリア判定
        if px == 7 and py == 7:
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
