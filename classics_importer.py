# -*- coding: utf-8 -*-
"""经典文库数据导入器。

支持从 JSON 文件批量导入，可复用外部传入的 :class:`ClassicsDatabase`
实例，避免同一数据库被打开多个连接。
"""
import json
import os

from classics_database import ClassicsDatabase
from utils import resource_path


class ClassicsImporter:
    def __init__(self, db_path="data/classics.db", db=None):
        self.db = db or ClassicsDatabase(db_path)

    @staticmethod
    def _validate_item(item):
        """校验并补全字段；缺少标题或正文时返回 None。"""
        if not isinstance(item, dict):
            return None
        title = str(item.get("title", "")).strip()
        content = str(item.get("content", "")).strip()
        if not title or not content:
            return None
        item["title"] = title
        item["content"] = content
        item.setdefault("author", "佚名")
        item.setdefault("dynasty", "未知")
        item.setdefault("category", "未分类")
        item.setdefault("subcategory", "")
        item.setdefault("translation", "")
        item.setdefault("annotation", "")
        item.setdefault("tags", "")
        item.setdefault("source", "")
        item.setdefault("is_famous", 0)
        item.setdefault("difficulty_level", 2)
        return item

    def import_from_json(self, json_path):
        """从 JSON 文件导入；支持数组或 ``{分类: [条目]}`` 两种结构。"""
        with open(json_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)

        count = 0
        if isinstance(data, list):
            for item in data:
                valid = self._validate_item(item)
                if valid and self.db.insert(valid):
                    count += 1
        elif isinstance(data, dict):
            for category, items in data.items():
                if not isinstance(items, list):
                    continue
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    item.setdefault("category", category)
                    valid = self._validate_item(item)
                    if valid and self.db.insert(valid):
                        count += 1
        self.db.improve_data_quality()
        return count

    def import_bundled_seed(self):
        """导入随安装包分发的经典种子，按标题/作者合并，返回新增数量。"""
        path = resource_path("resources", "classics_seed.json")
        if not os.path.exists(path):
            return 0
        try:
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError):
            return 0
        records = payload.get("records", []) if isinstance(payload, dict) else payload
        added = 0
        matched_legacy = set()
        for item in records if isinstance(records, list) else []:
            valid = self._validate_item(dict(item))
            if not valid:
                continue
            existing = self.db.conn.execute(
                "SELECT id FROM classics WHERE id=? LIMIT 1", (valid.get("id", ""),)
            ).fetchone()
            if existing is None:
                # 只和旧库条目合并；种子内部同题作品（如不同词牌的宋词）按 ID 各自保留
                candidates = self.db.conn.execute(
                    "SELECT id FROM classics WHERE title=? AND author=? AND id NOT LIKE 'cur_%'",
                    (valid["title"], valid.get("author", "佚名")),
                ).fetchall()
                existing = next((row for row in candidates if row["id"] not in matched_legacy), None)
                if existing is not None:
                    matched_legacy.add(existing["id"])
            if existing:
                # 已有用户数据：只补权威字段，保留原 ID（笔记/收藏不丢）
                self.db.conn.execute(
                    """UPDATE classics SET dynasty=?, category=?, subcategory=?, content=?,
                       annotation=CASE WHEN ?<>'' THEN ? ELSE annotation END,
                       tags=CASE WHEN ?<>'' THEN ? ELSE tags END, source=?, char_count=?,
                       is_famous=?, difficulty_level=?, verified=?, updated_at=CURRENT_TIMESTAMP
                       WHERE id=?""",
                    (
                        valid.get("dynasty", "未知"), valid.get("category", "未分类"),
                        valid.get("subcategory", ""), valid.get("content", ""),
                        valid.get("annotation", ""), valid.get("annotation", ""),
                        valid.get("tags", ""), valid.get("tags", ""), valid.get("source", ""),
                        len(valid.get("content", "")), int(valid.get("is_famous", 0) or 0),
                        int(valid.get("difficulty_level", 2) or 2), int(valid.get("verified", 0) or 0),
                        existing["id"],
                    ),
                )
                continue
            if self.db.insert(valid, commit=False):
                added += 1
                matched_legacy.add(valid.get("id", ""))
        self.db.conn.commit()
        self.db.improve_data_quality()
        return added

    def import_sample_data(self):
        """导入内置示例数据（诸子百家 + 经典散文核心篇目）。"""
        sample_data = self._sample_data()
        processed = [self._validate_item(item) for item in sample_data]
        processed = [item for item in processed if item]
        count = self.db.batch_insert(processed)
        self.db.improve_data_quality()
        return count

    def get_stats(self):
        return self.db.get_stats()

    @staticmethod
    def _sample_data():
        return [
            {
                "id": "zhuzi_001",
                "title": "逍遥游（节选）",
                "author": "庄子",
                "dynasty": "先秦",
                "category": "诸子百家",
                "subcategory": "道家",
                "content": "北冥有鱼，其名为鲲。鲲之大，不知其几千里也。化而为鸟，其名为鹏。鹏之背，不知其几千里也。怒而飞，其翼若垂天之云。是鸟也，海运则将徙于南冥。南冥者，天池也。\n\n《齐谐》者，志怪者也。《谐》之言曰：\"鹏之徙于南冥也，水击三千里，抟扶摇而上者九万里，去以六月息者也。\"\n\n天之苍苍，其正色邪？其远而无所至极邪？其视下也，亦若是则已矣。且夫水之积也不厚，则其负大舟也无力。覆杯水于坳堂之上，则芥为之舟；置杯焉则胶，水浅而舟大也。风之积也不厚，则其负大翼也无力。故九万里，则风斯在下矣，而后乃今培风；背负青天而莫之夭阏者，而后乃今将图南。",
                "annotation": "庄子《逍遥游》开篇，以鲲鹏之大比喻超越世俗限制的精神自由。'逍遥'是庄子哲学的核心概念。",
                "tags": ["道家", "逍遥", "自由", "鲲鹏"],
                "is_famous": 1,
            },
            {
                "id": "zhuzi_002",
                "title": "鱼我所欲也",
                "author": "孟子",
                "dynasty": "先秦",
                "category": "诸子百家",
                "subcategory": "儒家",
                "content": "鱼，我所欲也；熊掌，亦我所欲也。二者不可得兼，舍鱼而取熊掌者也。生，亦我所欲也；义，亦我所欲也。二者不可得兼，舍生而取义者也。\n\n生亦我所欲，所欲有甚于生者，故不为苟得也；死亦我所恶，所恶有甚于死者，故患有所不辟也。如使人之所欲莫甚于生，则凡可以得生者，何不用也？使人之所恶莫甚于死者，则凡可以辟患者，何不为也？由是则生而有不用也，由是则可以辟患而有不为也。是故所欲有甚于生者，所恶有甚于死者。非独贤者有是心也，人皆有之，贤者能勿丧耳。",
                "annotation": "孟子以鱼与熊掌的比喻，阐述舍生取义的道德选择，体现了儒家对道义的坚守。",
                "tags": ["儒家", "舍生取义", "道义", "孟子"],
                "is_famous": 1,
            },
            {
                "id": "sanwen_001",
                "title": "兰亭集序",
                "author": "王羲之",
                "dynasty": "东晋",
                "category": "经典散文",
                "subcategory": "序跋",
                "content": "永和九年，岁在癸丑，暮春之初，会于会稽山阴之兰亭，修禊事也。群贤毕至，少长咸集。此地有崇山峻岭，茂林修竹，又有清流激湍，映带左右，引以为流觞曲水，列坐其次。虽无丝竹管弦之盛，一觞一咏，亦足以畅叙幽情。\n\n是日也，天朗气清，惠风和畅。仰观宇宙之大，俯察品类之盛，所以游目骋怀，足以极视听之娱，信可乐也。\n\n夫人之相与，俯仰一世。或取诸怀抱，悟言一室之内；或因寄所托，放浪形骸之外。虽趣舍万殊，静躁不同，当其欣于所遇，暂得于己，快然自足，不知老之将至。及其所之既倦，情随事迁，感慨系之矣。向之所欣，俯仰之间，已为陈迹，犹不能不以之兴怀。况修短随化，终期于尽。古人云：\"死生亦大矣。\"岂不痛哉！\n\n每览昔人兴感之由，若合一契，未尝不临文嗟悼，不能喻之于怀。固知一死生为虚诞，齐彭殇为妄作。后之视今，亦犹今之视昔。悲夫！故列叙时人，录其所述，虽世殊事异，所以兴怀，其致一也。后之览者，亦将有感于斯文。",
                "annotation": "千古名篇，以兰亭雅集抒发对人生短暂的感慨。'死生亦大矣'、'后之视今，亦犹今之视昔'成为千古名言。",
                "tags": ["兰亭", "雅集", "生死", "书法"],
                "is_famous": 1,
            },
            {
                "id": "sanwen_002",
                "title": "归去来兮辞（并序）",
                "author": "陶渊明",
                "dynasty": "东晋",
                "category": "经典散文",
                "subcategory": "辞赋",
                "content": "归去来兮，田园将芜胡不归？既自以心为形役，奚惆怅而独悲？悟已往之不谏，知来者之可追。实迷途其未远，觉今是而昨非。舟遥遥以轻飏，风飘飘而吹衣。问征夫以前路，恨晨光之熹微。\n\n乃瞻衡宇，载欣载奔。僮仆欢迎，稚子候门。三径就荒，松菊犹存。携幼入室，有酒盈樽。引壶觞以自酌，眄庭柯以怡颜。倚南窗以寄傲，审容膝之易安。园日涉以成趣，门虽设而常关。策扶老以流憩，时矫首而遐观。云无心以出岫，鸟倦飞而知还。景翳翳以将入，抚孤松而盘桓。\n\n归去来兮，请息交以绝游。世与我而相违，复驾言兮焉求？悦亲戚之情话，乐琴书以消忧。农人告余以春及，将有事于西畴。或命巾车，或棹孤舟。既窈窕以寻壑，亦崎岖而经丘。木欣欣以向荣，泉涓涓而始流。善万物之得时，感吾生之行休。\n\n已矣乎！寓形宇内复几时？曷不委心任去留？胡为乎遑遑欲何之？富贵非吾愿，帝乡不可期。怀良辰以孤往，或植杖而耘耔。登东皋以舒啸，临清流而赋诗。聊乘化以归尽，乐夫天命复奚疑！",
                "annotation": "陶渊明辞官归隐的宣言，'云无心以出岫，鸟倦飞而知还'表达了回归田园、追求心灵自由的愿望。",
                "tags": ["隐逸", "田园", "自由", "辞官"],
                "is_famous": 1,
            },
            {
                "id": "sanwen_003",
                "title": "岳阳楼记",
                "author": "范仲淹",
                "dynasty": "北宋",
                "category": "经典散文",
                "subcategory": "记",
                "content": "庆历四年春，滕子京谪守巴陵郡。越明年，政通人和，百废具兴。乃重修岳阳楼，增其旧制，刻唐贤今人诗赋于其上。属予作文以记之。\n\n予观夫巴陵胜状，在洞庭一湖。衔远山，吞长江，浩浩汤汤，横无际涯；朝晖夕阴，气象万千。此则岳阳楼之大观也，前人之述备矣。然则北通巫峡，南极潇湘，迁客骚人，多会于此，览物之情，得无异乎？\n\n若夫霪雨霏霏，连月不开，阴风怒号，浊浪排空；日星隐曜，山岳潜形；商旅不行，樯倾楫摧；薄暮冥冥，虎啸猿啼。登斯楼也，则有去国怀乡，忧谗畏讥，满目萧然，感极而悲者矣。\n\n至若春和景明，波澜不惊，上下天光，一碧万顷；沙鸥翔集，锦鳞游泳；岸芷汀兰，郁郁青青。而或长烟一空，皓月千里，浮光跃金，静影沉璧，渔歌互答，此乐何极！登斯楼也，则有心旷神怡，宠辱偕忘，把酒临风，其喜洋洋者矣。\n\n嗟夫！予尝求古仁人之心，或异二者之为，何哉？不以物喜，不以己悲；居庙堂之高则忧其民；处江湖之远则忧其君。是进亦忧，退亦忧。然则何时而乐耶？其必曰\"先天下之忧而忧，后天下之乐而乐\"乎。噫！微斯人，吾谁与归？",
                "annotation": "千古名篇，'先天下之忧而忧，后天下之乐而乐'成为士大夫精神的最高典范，影响深远。",
                "tags": ["岳阳楼", "忧国", "士大夫", "洞庭湖"],
                "is_famous": 1,
            },
            {
                "id": "sanwen_004",
                "title": "醉翁亭记",
                "author": "欧阳修",
                "dynasty": "北宋",
                "category": "经典散文",
                "subcategory": "记",
                "content": "环滁皆山也。其西南诸峰，林壑尤美。望之蔚然而深秀者，琅琊也。山行六七里，渐闻水声潺潺，而泻出于两峰之间者，酿泉也。峰回路转，有亭翼然临于泉上者，醉翁亭也。作亭者谁？山之僧智仙也。名之者谁？太守自谓也。太守与客来饮于此，饮少辄醉，而年又最高，故自号曰醉翁也。醉翁之意不在酒，在乎山水之间也。山水之乐，得之心而寓之酒也。\n\n若夫日出而林霏开，云归而岩穴暝，晦明变化者，山间之朝暮也。野芳发而幽香，佳木秀而繁阴，风霜高洁，水落而石出者，山间之四时也。朝而往，暮而归，四时之景不同，而乐亦无穷也。\n\n至于负者歌于途，行者休于树，前者呼，后者应，伛偻提携，往来而不绝者，滁人游也。临溪而渔，溪深而鱼肥；酿泉为酒，泉香而酒洌；山肴野蔌，杂然而前陈者，太守宴也。宴酣之乐，非丝非竹，射者中，弈者胜，觥筹交错，起坐而喧哗者，众宾欢也。苍颜白发，颓然乎其间者，太守醉也。\n\n已而夕阳在山，人影散乱，太守归而宾客从也。树林阴翳，鸣声上下，游人去而禽鸟乐也。然而禽鸟知山林之乐，而不知人之乐；人知从太守游而乐，而不知太守之乐其乐也。醉能同其乐，醒能述以文者，太守也。太守谓谁？庐陵欧阳修也。",
                "annotation": "欧阳修被贬滁州时所作，'醉翁之意不在酒'表达了豁达胸襟和与民同乐的为政理念。",
                "tags": ["醉翁亭", "山水", "太守", "与民同乐"],
                "is_famous": 1,
            },
            {
                "id": "sanwen_005",
                "title": "滕王阁序",
                "author": "王勃",
                "dynasty": "初唐",
                "category": "经典散文",
                "subcategory": "骈文",
                "content": "豫章故郡，洪都新府。星分翼轸，地接衡庐。襟三江而带五湖，控蛮荆而引瓯越。物华天宝，龙光射牛斗之墟；人杰地灵，徐孺下陈蕃之榻。雄州雾列，俊采星驰。台隍枕夷夏之交，宾主尽东南之美。\n\n时维九月，序属三秋。潦水尽而寒潭清，烟光凝而暮山紫。俨骖騑于上路，访风景于崇阿。临帝子之长洲，得仙人之旧馆。层台耸翠，上出重霄；飞阁流丹，下临无地。鹤汀凫渚，穷岛屿之萦回；桂殿兰宫，即冈峦之体势。\n\n披绣闼，俯雕甍，山原旷其盈视，川泽纡其骇瞩。闾阎扑地，钟鸣鼎食之家；舸舰弥津，青雀黄龙之舳。云销雨霁，彩彻区明。落霞与孤鹜齐飞，秋水共长天一色。渔舟唱晚，响穷彭蠡之滨；雁阵惊寒，声断衡阳之浦。\n\n嗟乎！时运不齐，命途多舛。冯唐易老，李广难封。屈贾谊于长沙，非无圣主；窜梁鸿于海曲，岂乏明时？所赖君子见机，达人知命。老当益壮，宁移白首之心？穷且益坚，不坠青云之志。酌贪泉而觉爽，处涸辙以犹欢。北海虽赊，扶摇可接；东隅已逝，桑榆非晚。\n\n勃，三尺微命，一介书生。无路请缨，等终军之弱冠；有怀投笔，慕宗悫之长风。舍簪笏于百龄，奉晨昏于万里。非谢家之宝树，接孟氏之芳邻。他日趋庭，叨陪鲤对；今兹捧袂，喜托龙门。杨意不逢，抚凌云而自惜；钟期既遇，奏流水以何惭？\n\n呜乎！胜地不常，盛筵难再；兰亭已矣，梓泽丘墟。临别赠言，幸承恩于伟饯；登高作赋，是所望于群公。敢竭鄙怀，恭疏短引；一言均赋，四韵俱成：\n\n滕王高阁临江渚，佩玉鸣鸾罢歌舞。\n画栋朝飞南浦云，珠帘暮卷西山雨。\n闲云潭影日悠悠，物换星移几度秋。\n阁中帝子今何在？槛外长江空自流。",
                "annotation": "初唐四杰之首王勃的传世名篇，'落霞与孤鹜齐飞，秋水共长天一色'为千古绝唱。'老当益壮，宁移白首之心？穷且益坚，不坠青云之志'激励了无数后人。",
                "tags": ["滕王阁", "骈文", "落霞", "壮志"],
                "is_famous": 1,
            },
        ]
