#データ検証用ファイル
import re  # 正規表現処理用
import unicodedata  # 全角・半角変換用

# =========================================================
# ★ 新規ユーザー登録のためのデータ検証関数
# =========================================================


def parse_and_validate_registration_data(user_text):
    """
    ユーザー入力をパースし、指定された厳格なルールで検証する
    """

    # 1. 前処理: 全角スペースを半角に変換し、連続するスペースを1つにまとめる
    normalized_text = user_text.replace("　", " ").strip()

    # 【検証 1: 分割と要素数のチェック】
    # 複数のスペースを1つのスペースに置き換え、分割する
    parts = re.split(r"\s+", normalized_text)

    if len(parts) != 4:
        return {
            "error": "入力された情報が不足しています。**学年・クラス・姓・名**をすべてスペース区切りで入力してください。"
        }

    grade, user_class, last_name, first_name = parts

    # 【検証 2: 学年とクラスの厳格なチェック（「年」や「組」の混入防止）】

    # 学年 (1〜3の数字)
    grade_num_str = unicodedata.normalize("NFKC", grade)  # 全角数字を半角に
    if not grade_num_str.isdigit() or not (1 <= int(grade_num_str) <= 3):
        return {"error": "学年は1から3の数字のみを入力してください。（例: '2'）"}

    # クラス (数字のみ)
    user_class_num_str = unicodedata.normalize("NFKC", user_class)  # 全角数字を半角に
    if not user_class_num_str.isdigit():
        return {"error": "クラスは数字のみを入力してください。（例: 'A'ではなく'1'）"}

    # 【検証 3: 姓・名のチェック（数字、記号の禁止）】
    # 漢字、ひらがな、カタカナ、英字以外を禁止する正規表現
    # ただし、姓や名が空の場合は弾く
    name_pattern = re.compile(r"^[ぁ-んァ-ヶ一-龠a-zA-Z]+$")

    if not name_pattern.match(last_name):
        return {
            "error": f"姓（{last_name}）に数字や記号を含めることはできません。文字のみで入力してください。"
        }

    if not name_pattern.match(first_name):
        return {
            "error": f"名（{first_name}）に数字や記号を含めることはできません。文字のみで入力してください。"
        }

    # 検証にすべて成功した場合
    return {
        "success": True,
        "data": {
            "grade": int(grade_num_str),
            "class": int(user_class_num_str),
            "last_name": last_name,
            "first_name": first_name,
        },
    }