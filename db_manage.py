"""
数据库管理工具

提供数据库初始化、迁移、查看统计等命令行功能。

用法：
  python db_manage.py init          # 初始化数据库（创建表）
  python db_manage.py migrate       # 从JSON迁移数据到数据库
  python db_manage.py stats         # 查看数据统计
  python db_manage.py battles N     # 查看最近N场对战记录
  python db_match A B               # 查询A队对B队的胜率
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sim.data_store import (
    get_config,
    init_db,
    migrate_experience_from_json,
    migrate_pokemon_from_json,
    DataStore,
)


def cmd_init():
    """初始化数据库"""
    config = get_config()
    print(f"\n  [配置] 数据库: {config['name']}")
    print(f"  [配置] 地址: {config['host']}:{config['port']}")
    
    success = init_db(config)
    if success:
        print("  ✓ 数据库初始化成功！")
    else:
        print("  ✗ 数据库初始化失败！")


def cmd_migrate():
    """从JSON迁移数据到数据库"""
    config = get_config()
    
    print("\n  [迁移] 开始从JSON文件迁移数据...")
    
    # 迁移经验数据
    if os.path.exists(os.path.join(os.path.dirname(__file__), "data", "experience")):
        migrate_experience_from_json(config)
    else:
        print("  [跳过] 经验目录不存在")
    
    # 迁移精灵数据
    pokemon_path = os.path.join(os.path.dirname(__file__), "data", "sprites.json")
    if os.path.exists(pokemon_path):
        migrate_pokemon_from_json(config)
    else:
        print("  [跳过] 精灵JSON文件不存在")
    
    print("\n  ✓ 迁移完成！")


def cmd_stats():
    """查看数据统计"""
    config = get_config()
    store = DataStore(config)
    
    if not store.use_database():
        print("\n  [提示] 当前使用JSON后端，数据库统计不可用")
        return
    
    from sim.data_store import get_engine, ExperienceRecord, BattleRecord, PokemonRecord
    from sqlalchemy.orm import sessionmaker
    
    engine = get_engine(config)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    
    try:
        exp_count = session.query(ExperienceRecord).count()
        battle_count = session.query(BattleRecord).count()
        pokemon_count = session.query(PokemonRecord).count() if PokemonRecord else 0
        
        print(f"\n  [数据统计]")
        print(f"    经验记录: {exp_count}")
        print(f"    对战记录: {battle_count}")
        if pokemon_count:
            print(f"    精灵数据: {pokemon_count}")
    except Exception as e:
        print(f"\n  [!] 统计查询失败: {e}")
    finally:
        session.close()


def cmd_battles(limit=10):
    """查看最近的对战记录"""
    config = get_config()
    store = DataStore(config)
    
    if not store.use_database():
        print("\n  [提示] 当前使用JSON后端，对战统计不可用")
        return
    
    records = store.get_battle_stats(limit=limit)
    
    if not records:
        print("\n  [空] 暂无对战记录")
        return
    
    print(f"\n  [最近 {len(records)} 场对战]")
    print(f"  {'A队':<12} {'B队':<12} {'胜者':<6} {'回合':>4} {'耗时':>8}")
    print("  " + "-" * 50)
    
    for r in records:
        winner_str = f"{r['team_a']}✓" if r["winner"] == "a" else (f"{r['team_b']}✓" if r["winner"] == "b" else "平局")
        print(f"  {r['team_a']:<12} {r['team_b']:<12} {winner_str:<6} {r['turns']:>4} {r['elapsed_ms']/1000:.1f}s")


def cmd_match(team_a: str, team_b: str):
    """查询A队对B队的胜率"""
    config = get_config()
    store = DataStore(config)
    
    if not store.use_database():
        print("\n  [提示] 当前使用JSON后端，胜率统计不可用")
        return
    
    win_rate = store.get_win_rate(team_a, team_b)
    
    if win_rate is None:
        print(f"\n  [空] {team_a} vs {team_b}: 暂无对战数据")
    else:
        print(f"\n  [{team_a} vs {team_b}] 胜率: {win_rate*100:.1f}%")


def main():
    if len(sys.argv) < 2:
        print("\n  数据库管理工具")
        print("  用法: python db_manage.py <命令> [参数]")
        print("\n  命令:")
        print("    init          - 初始化数据库（创建表）")
        print("    migrate       - 从JSON迁移数据到数据库")
        print("    stats         - 查看数据统计")
        print("    battles N     - 查看最近N场对战记录")
        print("    match A B     - 查询A队对B队的胜率")
        return
    
    cmd = sys.argv[1].lower()
    
    if cmd == "init":
        cmd_init()
    elif cmd == "migrate":
        cmd_migrate()
    elif cmd == "stats":
        cmd_stats()
    elif cmd == "battles":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        cmd_battles(limit)
    elif cmd == "match":
        if len(sys.argv) < 4:
            print("\n  [!] 用法: python db_manage.py match A队名 B队名")
            return
        cmd_match(sys.argv[2], sys.argv[3])
    else:
        print(f"\n  [!] 未知命令: {cmd}")


if __name__ == "__main__":
    main()
