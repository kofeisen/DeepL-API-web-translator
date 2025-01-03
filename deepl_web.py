from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Response
import requests
import logging
import os
import csv
import io
import json

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# 修改日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # 输出到控制台
        logging.FileHandler('deepl_translation.log')  # 同时写入文件
    ]
)

DEEPL_API_URLS = {
    "Free": "https://api-free.deepl.com/v2/document",
    "Pro": "https://api.deepl.com/v2/document"
}

# DeepL支持的语言列表
LANGUAGES = {
    'ZH': '中文',
    'EN': 'English',
    'DE': 'Deutsch',
    'FR': 'Français',
    'ES': 'Español',
    'IT': 'Italiano',
    'JA': '日本語',
    'KO': '한국어',
    'RU': 'Русский',
    'PT': 'Português',
    'NL': 'Nederlands'
}

# 修改默认语言设置
DEFAULT_SOURCE_LANG = 'EN'
DEFAULT_TARGET_LANG = 'ZH'

@app.route('/', methods=['GET', 'POST'])
def index():
    document_info = None
    if request.method == 'POST' and request.form.get('submit_type') == 'translate':
        api_key = request.form['api_key']
        api_url = request.form['api_url']
        source_lang = request.form['source_lang']
        target_lang = request.form['target_lang']
        glossary_id = request.form.get('glossary_id', '')
        file = request.files.get('file')

        if not file:
            flash('请上传一个文件')
            logging.warning('No file uploaded')
            return redirect(url_for('index'))

        try:
            filename = file.filename
            logging.info(f'Uploading file: {filename}')
            
            data = {
                'auth_key': api_key,
                'source_lang': source_lang,
                'target_lang': target_lang
            }
            
            if glossary_id:
                data['glossary_id'] = glossary_id
                logging.info(f'Using glossary ID: {glossary_id}')
            
            files = {
                'file': (filename, file.stream, file.content_type)
            }
            
            response = requests.post(
                api_url,
                files=files,
                data=data
            )
            
            logging.info(f'API Response: {response.text}')
            
            if response.status_code == 200:
                result = response.json()
                document_info = {
                    'document_id': result.get('document_id'),
                    'document_key': result.get('document_key'),
                    'status': 'uploaded',
                    'filename': filename,
                    'source_lang': source_lang,
                    'target_lang': target_lang,
                    'glossary_id': glossary_id
                }
                logging.info(f'Document uploaded successfully: {document_info}')
                flash('文件上传成功！')
            else:
                error_message = response.json().get('message', '未知错误')
                flash(f'上传失败：{error_message}')
                logging.error(f'Upload failed with status code: {response.status_code}, message: {error_message}')
        
        except Exception as e:
            flash('发生错误，请稍后重试')
            logging.error(f'Error during upload: {str(e)}')

    return render_template('index.html', 
                         api_urls=DEEPL_API_URLS,
                         languages=LANGUAGES,
                         document_info=document_info,
                         request=request,
                         default_source_lang=DEFAULT_SOURCE_LANG,
                         default_target_lang=DEFAULT_TARGET_LANG)

@app.route('/check_status', methods=['POST'])
def check_status():
    data = request.json
    api_key = data.get('api_key')
    api_url = data.get('api_url')
    document_id = data.get('document_id')
    document_key = data.get('document_key')

    try:
        # 检查翻译状态
        status_url = f"{api_url}/{document_id}"
        response = requests.get(
            status_url,
            params={
                'auth_key': api_key,
                'document_key': document_key
            }
        )
        
        logging.info(f'Status check response: {response.text}')
        
        if response.status_code == 200:
            status_data = response.json()
            return jsonify(status_data)
        else:
            logging.error(f'Status check failed: {response.status_code}')
            return jsonify({'error': '状态检查失败'}), 400

    except Exception as e:
        logging.error(f'Error checking status: {str(e)}')
        return jsonify({'error': str(e)}), 500

@app.route('/download_document', methods=['POST'])
def download_document():
    try:
        data = request.json
        api_key = data.get('api_key')
        api_url = data.get('api_url')
        document_id = data.get('document_id')
        document_key = data.get('document_key')

        if not all([api_key, document_id, document_key]):
            return jsonify({'error': '缺少必要参数'}), 400

        # 构建下载URL
        download_url = f"{api_url}/{document_id}/result"
        
        # 发送下载请求
        response = requests.get(
            download_url,
            headers={
                'Authorization': f'DeepL-Auth-Key {api_key}'
            },
            params={
                'document_key': document_key
            }
        )
        
        logging.info(f'Download response status: {response.status_code}')
        
        if response.status_code == 200:
            # 获取文件名
            content_disposition = response.headers.get('Content-Disposition', '')
            filename = content_disposition.split('filename=')[-1].strip('"') if 'filename=' in content_disposition else 'translated_document'
            
            # 返回文件内容
            return response.content, 200, {
                'Content-Type': response.headers.get('Content-Type', 'application/octet-stream'),
                'Content-Disposition': f'attachment; filename="{filename}"'
            }
        else:
            error_message = response.json().get('message', '下载失败')
            logging.error(f'Download failed: {error_message}')
            return jsonify({'error': error_message}), response.status_code

    except Exception as e:
        logging.error(f'Error downloading document: {str(e)}')
        return jsonify({'error': str(e)}), 500

@app.route('/glossary', methods=['GET', 'POST'])
def glossary():
    if request.method == 'POST':
        action = request.form.get('action')
        api_key = request.form.get('api_key')
        api_url = request.form.get('api_url')
        
        # 修正 API 基础 URL 的构建
        if '/v2/document' in api_url:
            api_base_url = api_url.replace('/v2/document', '')
        elif '/document' in api_url:
            api_base_url = api_url.replace('/document', '')
        else:
            api_base_url = api_url

        try:
            if action == 'list':
                # 获取术语表列表
                glossaries_url = f"{api_base_url}/v2/glossaries"
                logging.info(f'Requesting glossaries from: {glossaries_url}')
                
                response = requests.get(
                    glossaries_url,
                    headers={'Authorization': f'DeepL-Auth-Key {api_key}'}
                )
                
                if response.status_code == 200:
                    try:
                        glossaries = response.json().get('glossaries', [])
                        return render_template('glossary.html', 
                                            api_urls=DEEPL_API_URLS,
                                            languages=LANGUAGES,
                                            glossaries=glossaries)
                    except json.JSONDecodeError as e:
                        error_message = f'JSON解析错误: {str(e)}, 响应内容: {response.text}'
                        flash(error_message)
                        logging.error(error_message)
                else:
                    error_message = f'请求失败 ({response.status_code}): {response.text}'
                    flash(error_message)
                    logging.error(error_message)

            elif action == 'download_tsv':
                glossary_id = request.form.get('glossary_id')
                entries_url = f"{api_base_url}/v2/glossaries/{glossary_id}/entries"
                
                response = requests.get(
                    entries_url,
                    headers={'Authorization': f'DeepL-Auth-Key {api_key}'}
                )
                
                logging.info(f'Download TSV Response Status: {response.status_code}')
                logging.info(f'Download TSV URL: {entries_url}')
                logging.info(f'Response Content Type: {response.headers.get("Content-Type")}')
                logging.info(f'Response Content: {response.text[:200]}')  # 记录响应内容的前200个字符
                
                if response.status_code == 200:
                    try:
                        # 检查内容类型
                        content_type = response.headers.get('Content-Type', '')
                        if 'application/json' in content_type:
                            entries = response.json()
                        else:
                            # 如果不是JSON格式，尝试解析TSV/CSV格式
                            content = response.text
                            entries = {}
                            for line in content.splitlines():
                                if line.strip():  # 跳过空行
                                    parts = line.split('\t')
                                    if len(parts) >= 2:
                                        entries[parts[0]] = parts[1]
                        
                        # 创建新的TSV文件
                        output = io.StringIO()
                        writer = csv.writer(output, delimiter='\t')
                        writer.writerow(['source_term', 'target_term'])  # 表头
                        
                        # 写入条目
                        if isinstance(entries, dict):
                            for source, target in entries.items():
                                writer.writerow([source, target])
                        elif isinstance(entries, list):
                            for entry in entries:
                                if isinstance(entry, dict):
                                    source = entry.get('source', '')
                                    target = entry.get('target', '')
                                    writer.writerow([source, target])
                        
                        # 返回TSV文件
                        return Response(
                            output.getvalue().encode('utf-8-sig'),
                            mimetype='text/tab-separated-values',
                            headers={
                                'Content-Disposition': 'attachment; filename=glossary.tsv'
                            }
                        )
                    except Exception as e:
                        error_message = f'处理术语表数据失败: {str(e)}\n响应内容: {response.text[:200]}'
                        logging.error(error_message)
                        return jsonify({'error': error_message}), 500
                else:
                    error_message = f'获取术语表失败 ({response.status_code}): {response.text}'
                    logging.error(error_message)
                    return jsonify({'error': error_message}), response.status_code

            elif action == 'delete':
                glossary_id = request.form.get('glossary_id')
                delete_url = f"{api_base_url}/v2/glossaries/{glossary_id}"
                
                response = requests.delete(
                    delete_url,
                    headers={'Authorization': f'DeepL-Auth-Key {api_key}'}
                )
                
                logging.info(f'Delete Glossary Response Status: {response.status_code}')
                
                if response.status_code == 204:  # DeepL API 返回 204 表示删除成功
                    return jsonify({'message': '删除成功'})
                else:
                    try:
                        error_data = response.json()
                        error_message = error_data.get('message', '未知错误')
                    except json.JSONDecodeError:
                        error_message = f'删除失败 ({response.status_code}): {response.text}'
                    return jsonify({'error': error_message}), response.status_code

            elif action == 'upload':
                try:
                    glossary_name = request.form.get('glossary_name')
                    source_lang = request.form.get('source_lang')
                    target_lang = request.form.get('target_lang')
                    tsv_file = request.files.get('tsv_file')

                    logging.info(f'Upload request - Name: {glossary_name}, Source: {source_lang}, Target: {target_lang}')

                    if not tsv_file:
                        return jsonify({'error': '请选择TSV文件'}), 400

                    # 读取并解析TSV文件
                    content = tsv_file.read().decode('utf-8-sig')
                    entries = []  # 改为列表格式
                    for line in content.splitlines():
                        if line.strip() and not line.startswith('source_term\ttarget_term'):
                            parts = line.split('\t')
                            if len(parts) >= 2:
                                # 每个条目都是一个字典，包含 source 和 target
                                entries.append({
                                    "source": parts[0].strip(),
                                    "target": parts[1].strip()
                                })

                    if not entries:
                        return jsonify({'error': 'TSV文件为空或格式不正确'}), 400

                    # 记录要发送的数据
                    request_data = {
                        'name': glossary_name,
                        'source_lang': source_lang,
                        'target_lang': target_lang,
                        'entries_format': 'tsv',  # 指定格式为 TSV
                        'entries': '\n'.join(f"{entry['source']}\t{entry['target']}" for entry in entries)  # 转换为TSV字符串
                    }
                    logging.info(f'Creating glossary with data: {json.dumps(request_data, ensure_ascii=False)}')

                    # 创建术语表
                    create_url = f"{api_base_url}/v2/glossaries"
                    create_response = requests.post(
                        create_url,
                        headers={
                            'Authorization': f'DeepL-Auth-Key {api_key}',
                            'Content-Type': 'application/json'
                        },
                        json=request_data
                    )

                    logging.info(f'Create glossary response - Status: {create_response.status_code}')
                    logging.info(f'Response content: {create_response.text}')

                    if create_response.status_code == 201:
                        return jsonify({'message': '术语表创建成功'})
                    else:
                        try:
                            error_data = create_response.json()
                            error_message = error_data.get('message', '未知错误')
                            if 'detail' in error_data:
                                error_message += f": {error_data['detail']}"
                            logging.error(f'Create glossary error: {error_message}')
                        except json.JSONDecodeError:
                            error_message = f'创建失败 ({create_response.status_code}): {create_response.text}'
                            logging.error(f'Failed to parse error response: {create_response.text}')
                        return jsonify({'error': error_message}), create_response.status_code

                except Exception as e:
                    error_message = f'上传处理失败: {str(e)}'
                    logging.error(f'Upload exception: {str(e)}')
                    return jsonify({'error': error_message}), 500

        except requests.RequestException as e:
            error_message = f'请求错误: {str(e)}'
            logging.error(f'Request Exception: {error_message}')
            if action in ['download_tsv', 'upload']:
                return jsonify({'error': error_message}), 500
            else:
                flash(error_message)
        except Exception as e:
            error_message = f'未知错误: {str(e)}'
            logging.error(f'Unexpected Error: {error_message}')
            if action in ['download_tsv', 'upload']:
                return jsonify({'error': error_message}), 500
            else:
                flash(error_message)

    return render_template('glossary.html', 
                         api_urls=DEEPL_API_URLS,
                         languages=LANGUAGES,
                         glossaries=[])

if __name__ == '__main__':
    app.run(debug=True) 