# -*- coding: utf-8 -*-
class TTSManager:
    VOICES = {
        "female": {"name":"女声","rate":0.8,"pitch":1.2},
        "male": {"name":"男声","rate":0.8,"pitch":0.8},
        "child": {"name":"童声","rate":0.7,"pitch":1.5},
        "elder": {"name":"老者","rate":0.6,"pitch":0.6},
    }
    STYLES = {
        "normal": {"name":"朗读","rate":0.8},
        "chant": {"name":"吟诵","rate":0.5,"pitch":1.0},
        "rap": {"name":"说唱","rate":1.3,"pitch":0.9},
        "sing": {"name":"歌唱","rate":0.6,"pitch":1.1},
    }
    BGM = {"guqin":"古琴","dizi":"笛子","pipa":"琵琶","none":"无配乐"}
    @classmethod
    def get_voices(cls): return [{"id":k,"name":v["name"]} for k,v in cls.VOICES.items()]
    @classmethod
    def get_styles(cls): return [{"id":k,"name":v["name"]} for k,v in cls.STYLES.items()]
    @classmethod
    def get_bgm(cls): return [{"id":k,"name":v} for k,v in cls.BGM.items()]