import pytest
from pathlib import Path
from backend.rag import SQLiteVectorStore
from backend.skills import SkillRegistry

def test_skill_registry_and_tools(tmp_path):
    db_file = tmp_path / "test_skills.db"
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    
    # Tạo skill mẫu
    sample_skill_dir = skills_dir / "sample-skill"
    sample_skill_dir.mkdir()
    skill_file = sample_skill_dir / "SKILL.md"
    skill_file.write_text(
        "---\nname: sample-skill\ndescription: Kỹ năng mẫu thử nghiệm\n---\nNội dung hướng dẫn chi tiết của sample skill.",
        encoding="utf-8"
    )
    
    # Tạo file trong references
    ref_dir = sample_skill_dir / "references"
    ref_dir.mkdir()
    ref_file = ref_dir / "guide.txt"
    ref_file.write_text("Tài liệu tham khảo chuyên sâu", encoding="utf-8")
    
    store = SQLiteVectorStore(db_path=str(db_file))
    registry = SkillRegistry(skills_dir=skills_dir, vector_store=store)
    
    # 1. Kiểm tra nạp skill
    assert "sample-skill" in registry.skills_cache
    skill = registry.skills_cache["sample-skill"]
    assert skill["description"] == "Kỹ năng mẫu thử nghiệm"
    
    # 2. Kiểm tra use_skill
    content = registry.use_skill("sample-skill")
    assert "Nội dung hướng dẫn chi tiết" in content
    
    # 3. Kiểm tra read_skill_file
    ref_content = registry.read_skill_file("sample-skill", "guide.txt")
    assert "Tài liệu tham khảo chuyên sâu" in ref_content
    
    # 4. Kiểm tra chống Path Traversal
    traversal_res = registry.read_skill_file("sample-skill", "../../outside.txt")
    assert "vi phạm bảo mật" in traversal_res.lower()
    
    # 5. Kiểm tra lệnh /tên-skill tường minh
    cmd, remaining = registry.extract_explicit_skill_command("/sample-skill Viết bài báo cáo")
    assert cmd == "sample-skill"
    assert remaining == "Viết bài báo cáo"
