"""
数据存储层 - 统一接口，支持JSON文件和MariaDB两种后端

架构设计：
  - DataStore类提供统一的读写接口
  - 根据.env配置自动选择后端
  - 首次启用数据库时自动从JSON迁移数据
"""

import os
import json
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime

# SQLAlchemy相关
from sqlalchemy import create_engine, Column, Integer, String, Float, Text, DateTime, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

Base = declarative_base()


# ============================================================
# 配置加载
# ============================================================

def _load_env(path: str = None) -> dict:
    """从.env文件加载配置"""
    config = {}
    env_path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
    if not os.path.exists(env_path):
        return config
    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            config[key.strip()] = value.strip()
    return config


def get_config() -> dict:
    """获取数据存储配置"""
    env = _load_env()
    return {
        "enabled": env.get("DB_ENABLED", "false").lower() == "true",
        "host": env.get("DB_HOST", "127.0.0.1"),
        "port": int(env.get("DB_PORT", 3306)),
        "user": env.get("DB_USER", "root"),
        "password": env.get("DB_PASSWORD", "root"),
        "name": env.get("DB_NAME", "rocom_data"),
    }


# ============================================================
# 数据库模型
# ============================================================

class ExperienceRecord(Base):
    """
    MCTS经验数据表
    
    存储(state_key, action_key) → (wins, total)的映射关系
    """
    __tablename__ = "experience_records"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    team = Column(String(1), nullable=False)  # "a" or "b"
    state_key = Column(Text, nullable=False)  # 状态指纹（可能较长，用TEXT）
    action_key = Column(String(64), nullable=False)  # 动作标识
    wins = Column(Float, default=0.0)  # 累计胜利值
    total = Column(Integer, default=0)  # 总次数
    
    __table_args__ = (
        Index("idx_exp_team_state", "team"),
        Index("idx_exp_lookup", "team", "action_key"),
    )


class BattleRecord(Base):
    """
    对战记录表
    
    存储每场对战的基本信息，用于后续分析和LLM教练系统
    """
    __tablename__ = "battle_records"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    team_a_name = Column(String(64), nullable=False)  # A队名称
    team_b_name = Column(String(64), nullable=False)  # B队名称
    winner = Column(String(1))  # "a", "b", or None
    turns = Column(Integer, default=0)  # 回合数
    elapsed_ms = Column(Integer, default=0)  # 耗时（毫秒）
    mcts_iters = Column(Integer, default=20)  # MCTS迭代次数
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index("idx_battle_time", "created_at"),
    )


class PokemonRecord(Base):
    """
    精灵数据表（可选，未来迁移精灵数据时使用）
    """
    __tablename__ = "pokemon_records"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), unique=True, nullable=False)  # 精灵名称
    data_json = Column(Text, nullable=False)  # 完整JSON数据
    created_at = Column(DateTime, default=datetime.utcnow)


# ============================================================
# 数据库引擎管理
# ============================================================

def get_engine(config: dict):
    """创建数据库引擎"""
    url = f"mysql+pymysql://{config['user']}:{config['password']}@{config['host']}:{config['port']}/{config['name']}?charset=utf8mb4"
    return create_engine(url, pool_pre_ping=True)


def init_db(config: dict) -> bool:
    """
    初始化数据库（创建表和必要的数据库）。
    
    Returns
    -------
    bool : True=成功/已存在，False=失败
    """
    try:
        # 先尝试连接MySQL创建数据库
        import pymysql
        conn = pymysql.connect(
            host=config["host"],
            port=config["port"],
            user=config["user"],
            password=config["password"]
        )
        with conn.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{config['name']}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        conn.close()
        
        # 创建表
        engine = get_engine(config)
        Base.metadata.create_all(engine)
        return True
    except Exception as e:
        print(f"  [!] 数据库初始化失败: {e}")
        return False


def drop_db(config: dict) -> bool:
    """
    删除所有表（危险操作！用于重置）。
    
    Returns
    -------
    bool : True=成功，False=失败
    """
    try:
        engine = get_engine(config)
        Base.metadata.drop_all(engine)
        return True
    except Exception as e:
        print(f"  [!] 数据库删除失败: {e}")
        return False


# ============================================================
# JSON文件路径
# ============================================================

def get_json_dir() -> str:
    """获取JSON数据目录"""
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "data", "experience"
    )


def get_pokemon_json_path() -> str:
    """获取精灵JSON路径"""
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "data", "sprites.json"
    )


# ============================================================
# 数据迁移：JSON → 数据库
# ============================================================

def migrate_experience_from_json(config: dict) -> bool:
    """
    将JSON经验数据迁移到数据库。
    
    Returns
    -------
    bool : True=成功，False=失败
    """
    json_dir = get_json_dir()
    if not os.path.exists(json_dir):
        print("  [!] JSON目录不存在，跳过迁移")
        return False
    
    engine = get_engine(config)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    
    total_records = 0
    batch_size = 500
    records_to_add = []
    seen_keys = {}  # {(team, state_key, action_key): (wins, total)} for dedup within JSON
    
    try:
        for filename in os.listdir(json_dir):
            if not filename.endswith(".json"):
                continue
            
            filepath = os.path.join(json_dir, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # 解析经验数据：{team: {state_key: {action_key: {"w": wins, "n": total}}}}
            for team, states in data.items():
                if not isinstance(states, dict):
                    continue
                if team not in ("a", "b"):
                    continue
                for state_key, actions in states.items():
                    if not isinstance(actions, dict):
                        continue
                    # 检查是否是标准格式（包含w和n键）
                    first_val = next(iter(actions.values()), None)
                    if isinstance(first_val, (int, float)):
                        # 旧格式：{state_key: {"w": wins, "n": total}}
                        wins = float(actions.get("w", 0))
                        total_count = int(actions.get("n", 0))
                        action_key = state_key.split("|")[-1] if "|" in state_key else "unknown"
                        
                        key = (team, state_key, action_key)
                        if key not in seen_keys:
                            seen_keys[key] = (wins, total_count)
                            records_to_add.append(ExperienceRecord(
                                team=team,
                                state_key=state_key,
                                action_key=action_key,
                                wins=wins,
                                total=total_count
                            ))
                        else:
                            sw, st = seen_keys[key]
                            seen_keys[key] = (sw + wins, st + total_count)
                    else:
                        # 新格式：{state_key: {action_key: {"w": wins, "n": total}}}
                        for action_key, stats in actions.items():
                            if not isinstance(stats, dict):
                                continue
                            wins = float(stats.get("w", 0))
                            total_count = int(stats.get("n", 0))
                            
                            key = (team, state_key, action_key)
                            if key not in seen_keys:
                                seen_keys[key] = (wins, total_count)
                                records_to_add.append(ExperienceRecord(
                                    team=team,
                                    state_key=state_key,
                                    action_key=action_key,
                                    wins=wins,
                                    total=total_count
                                ))
                            else:
                                sw, st = seen_keys[key]
                                seen_keys[key] = (sw + wins, st + total_count)
            
            print(f"  [迁移] {filename} → 数据库")
        
        # 批量插入（使用INSERT ... ON DUPLICATE KEY UPDATE）
        for i in range(0, len(records_to_add), batch_size):
            batch = records_to_add[i:i+batch_size]
            session.add_all(batch)
            session.commit()
            total_records += len(batch)
            print(f"  [进度] {min(i+len(batch), len(records_to_add))}/{len(records_to_add)}")
        
        print(f"  [迁移完成] 共导入 {total_records} 条经验记录")
        return True
    except Exception as e:
        session.rollback()
        print(f"  [!] 迁移失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        session.close()


def migrate_pokemon_from_json(config: dict) -> bool:
    """
    将精灵JSON数据迁移到数据库。
    
    Returns
    -------
    bool : True=成功，False=失败
    """
    json_path = get_pokemon_json_path()
    if not os.path.exists(json_path):
        print("  [!] 精灵JSON文件不存在，跳过迁移")
        return False
    
    engine = get_engine(config)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        total_records = 0
        # 精灵数据可能是list格式或dict格式，需要兼容
        if isinstance(data, list):
            for item in data:
                name = item.get("name", "unknown")
                existing = session.query(PokemonRecord).filter_by(name=name).first()
                if not existing:
                    record = PokemonRecord(
                        name=name,
                        data_json=json.dumps(item, ensure_ascii=False)
                    )
                    session.add(record)
                    total_records += 1
        elif isinstance(data, dict):
            for name, pdata in data.items():
                existing = session.query(PokemonRecord).filter_by(name=name).first()
                if not existing:
                    record = PokemonRecord(
                        name=name,
                        data_json=json.dumps(pdata, ensure_ascii=False)
                    )
                    session.add(record)
                    total_records += 1
        
        session.commit()
        print(f"  [迁移完成] 精灵数据：{total_records} 条记录")
        return True
    except Exception as e:
        session.rollback()
        print(f"  [!] 精灵迁移失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        session.close()


# ============================================================
# DataStore - 统一数据访问接口
# ============================================================

class DataStore:
    """
    数据存储的统一接口。
    
    根据配置自动选择后端（数据库或JSON文件）。
    支持经验数据的读写、对战记录的存储等。
    """
    
    def __init__(self, config: dict = None):
        self.config = config or get_config()
        self._use_db = self.config.get("enabled", False)
        
        if self._use_db:
            # 确保数据库已初始化
            init_db(self.config)
    
    @property
    def db_enabled(self) -> bool:
        """是否使用数据库后端（属性访问）"""
        return self._use_db
    
    def use_database(self) -> bool:
        """是否使用数据库后端"""
        return self._use_db
    
    # ----------------------------------------------------------
    # 经验数据操作
    # ----------------------------------------------------------
    
    def get_experience(self, team: str) -> Dict[str, Dict[str, Tuple[float, int]]]:
        """
        获取某队的全部经验数据。
        
        Returns
        -------
        dict : {state_key: {action_key: (wins, total)}}
        """
        if self._use_db:
            return self._get_experience_from_db(team)
        else:
            return self._get_experience_from_json(team)
    
    def save_experience(
        self,
        team: str,
        data: Dict[str, Dict[str, Tuple[float, int]]]
    ) -> None:
        """
        保存某队的经验数据。
        
        Parameters
        ----------
        team : "a" or "b"
        data : {state_key: {action_key: (wins, total)}}
        """
        if self._use_db:
            self._save_experience_to_db(team, data)
        else:
            self._save_experience_to_json(team, data)
    
    def record_battle(
        self,
        team_a_name: str,
        team_b_name: str,
        winner: Optional[str],
        turns: int,
        elapsed_ms: int,
        mcts_iters: int = 20
    ) -> None:
        """
        记录一场对战。
        
        Parameters
        ----------
        team_a_name : A队名称
        team_b_name : B队名称
        winner : "a", "b", or None
        turns : 回合数
        elapsed_ms : 耗时（毫秒）
        mcts_iters : MCTS迭代次数
        """
        if self._use_db:
            self._record_battle_to_db(
                team_a_name, team_b_name, winner, turns, elapsed_ms, mcts_iters
            )
    
    def get_battle_stats(self, limit: int = 10) -> List[dict]:
        """
        获取最近的对战统计。
        
        Returns
        -------
        list : [{team_a_name, team_b_name, winner, turns, ...}, ...]
        """
        if self._use_db:
            return self._get_battle_stats_from_db(limit)
        else:
            return []  # JSON后端暂不支持对战记录
    
    def get_win_rate(self, team_a_name: str, team_b_name: str) -> Optional[float]:
        """
        获取两队之间的胜率（A队对B队的胜率）。
        
        Returns
        -------
        float : A队胜率 (0.0-1.0)，无数据时返回None
        """
        if self._use_db:
            return self._get_win_rate_from_db(team_a_name, team_b_name)
        else:
            return None
    
    def update_experience(
        self,
        team: str,
        state_key: str,
        action_key: str,
        wins: float,
        total: int
    ) -> None:
        """
        更新单条经验记录（UPSERT）。
        
        Parameters
        ----------
        team : "a" or "b"
        state_key : 状态指纹
        action_key : 动作标识
        wins : 累计胜利值
        total : 总次数
        """
        if self._use_db:
            self._update_experience_in_db(team, state_key, action_key, wins, total)
    
    def get_all_experience(self) -> List[ExperienceRecord]:
        """
        获取所有经验记录。
        
        Returns
        -------
        list : [ExperienceRecord, ...]
        """
        if self._use_db:
            return self._get_all_experience_from_db()
        else:
            return []
    
    def update_total_games(self, name: str, total: int) -> None:
        """
        更新某队的总局数。
        
        Parameters
        ----------
        name : 队伍名称（用于标识）
        total : 总局数
        """
        # 暂不实现，因为当前数据库没有存储队伍名称对应的总局数的表
    
    def get_total_games(self, name: str) -> int:
        """
        获取某队的总局数。
        
        Returns
        -------
        int : 总局数
        """
        # 暂不实现，返回0
        return 0
    
    # ----------------------------------------------------------
    # 数据库后端实现
    # ----------------------------------------------------------
    
    def _get_experience_from_db(self, team: str) -> Dict[str, Dict[str, Tuple[float, int]]]:
        """从数据库读取经验数据"""
        engine = get_engine(self.config)
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()
        
        try:
            records = session.query(ExperienceRecord).filter_by(team=team).all()
            result = {}
            for r in records:
                if r.state_key not in result:
                    result[r.state_key] = {}
                result[r.state_key][r.action_key] = (float(r.wins), int(r.total))
            return result
        finally:
            session.close()
    
    def _save_experience_to_db(self, team: str, data: dict) -> None:
        """
        将经验数据保存到数据库。
        
        使用UPSERT逻辑：如果(state_key, action_key)已存在则累加，否则插入新记录。
        """
        engine = get_engine(self.config)
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()
        
        try:
            for state_key, actions in data.items():
                for action_key, (wins, total) in actions.items():
                    existing = session.query(ExperienceRecord).filter_by(
                        team=team,
                        state_key=state_key,
                        action_key=action_key
                    ).first()
                    
                    if existing:
                        existing.wins += float(wins)
                        existing.total += int(total)
                    else:
                        record = ExperienceRecord(
                            team=team,
                            state_key=state_key,
                            action_key=action_key,
                            wins=float(wins),
                            total=int(total)
                        )
                        session.add(record)
            
            session.commit()
        except Exception as e:
            session.rollback()
            print(f"  [!] 经验数据保存失败: {e}")
        finally:
            session.close()
    
    def _record_battle_to_db(self, team_a_name, team_b_name, winner, turns, elapsed_ms, mcts_iters) -> None:
        """记录对战到数据库"""
        engine = get_engine(self.config)
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()
        
        try:
            record = BattleRecord(
                team_a_name=team_a_name,
                team_b_name=team_b_name,
                winner=winner,
                turns=turns,
                elapsed_ms=elapsed_ms,
                mcts_iters=mcts_iters
            )
            session.add(record)
            session.commit()
        except Exception as e:
            session.rollback()
            print(f"  [!] 对战记录保存失败: {e}")
        finally:
            session.close()
    
    def _get_battle_stats_from_db(self, limit: int) -> List[dict]:
        """从数据库获取对战统计"""
        engine = get_engine(self.config)
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()
        
        try:
            records = session.query(BattleRecord).order_by(
                BattleRecord.created_at.desc()  # type: ignore
            ).limit(limit).all()
            
            return [
                {
                    "team_a": r.team_a_name,
                    "team_b": r.team_b_name,
                    "winner": r.winner,
                    "turns": r.turns,
                    "elapsed_ms": r.elapsed_ms,
                    "mcts_iters": r.mcts_iters,
                    "created_at": str(r.created_at),
                }
                for r in records
            ]
        finally:
            session.close()
    
    def _get_win_rate_from_db(self, team_a_name: str, team_b_name: str) -> Optional[float]:
        """
        计算A队对B队的胜率。
        
        考虑两种情况：
          - A是team_a时的胜率
          - B是team_b时的胜率（即A是team_b时B输的场次）
        """
        engine = get_engine(self.config)
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()
        
        try:
            # A作为team_a的情况
            records_a = session.query(BattleRecord).filter_by(
                team_a_name=team_a_name,
                team_b_name=team_b_name
            ).all()
            
            # B作为team_a（即A作为team_b）的情况
            records_b = session.query(BattleRecord).filter_by(
                team_a_name=team_b_name,
                team_b_name=team_a_name
            ).all()
            
            total_games = len(records_a) + len(records_b)
            if total_games == 0:
                return None
            
            a_wins = sum(1 for r in records_a if r.winner == "a")
            a_wins += sum(1 for r in records_b if r.winner == "b")
            
            return a_wins / total_games
        finally:
            session.close()
    
    def _update_experience_in_db(
        self,
        team: str,
        state_key: str,
        action_key: str,
        wins: float,
        total: int
    ) -> None:
        """
        更新单条经验记录（UPSERT）。
        
        如果记录已存在则累加wins和total，否则插入新记录。
        """
        engine = get_engine(self.config)
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()
        
        try:
            existing = session.query(ExperienceRecord).filter_by(
                team=team,
                state_key=state_key,
                action_key=action_key
            ).first()
            
            if existing:
                existing.wins += float(wins)
                existing.total += int(total)
            else:
                record = ExperienceRecord(
                    team=team,
                    state_key=state_key,
                    action_key=action_key,
                    wins=float(wins),
                    total=int(total)
                )
                session.add(record)
            
            session.commit()
        except Exception as e:
            session.rollback()
            print(f"  [!] 经验记录更新失败: {e}")
        finally:
            session.close()
    
    def _get_all_experience_from_db(self) -> List[ExperienceRecord]:
        """
        获取所有经验记录。
        
        Returns
        -------
        list : [ExperienceRecord, ...]
        """
        engine = get_engine(self.config)
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()
        
        try:
            return session.query(ExperienceRecord).all()
        finally:
            session.close()
    
    # ----------------------------------------------------------
    # JSON后端实现（保持原有逻辑）
    # ----------------------------------------------------------
    
    def _get_experience_from_json(self, team: str) -> Dict[str, Dict[str, Tuple[float, int]]]:
        """从JSON文件读取经验数据"""
        json_dir = get_json_dir()
        result = {}
        
        for filename in os.listdir(json_dir):
            if not filename.endswith(".json"):
                continue
            filepath = os.path.join(json_dir, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            if team in data:
                for state_key, actions in data[team].items():
                    result[state_key] = {}
                    for action_key, stats in actions.items():
                        result[state_key][action_key] = (
                            float(stats.get("w", 0)),
                            int(stats.get("n", 0))
                        )
        
        return result
    
    def _save_experience_to_json(self, team: str, data: dict) -> None:
        """
        将经验数据保存到JSON文件。
        
        注意：这里简化处理，直接写入到默认文件。
        完整实现需要按队伍名分离存储。
        """
        json_dir = get_json_dir()
        os.makedirs(json_dir, exist_ok=True)
        
        # 合并已有数据
        existing_path = os.path.join(json_dir, "combined.json")
        if os.path.exists(existing_path):
            with open(existing_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        else:
            existing = {"a": {}, "b": {}}
        
        # 更新数据
        for state_key, actions in data.items():
            if team not in existing:
                existing[team] = {}
            if state_key not in existing[team]:
                existing[team][state_key] = {}
            for action_key, (wins, total) in actions.items():
                if action_key not in existing[team][state_key]:
                    existing[team][state_key][action_key] = {"w": 0, "n": 0}
                existing[team][state_key][action_key]["w"] += float(wins)
                existing[team][state_key][action_key]["n"] += int(total)
        
        # 写入文件
        with open(existing_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False)
