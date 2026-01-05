/**
 * gommi_download_manager 플러그인 JavaScript
 */

// 설정 저장
function setting_save() {
    var form_data = getFormdata('#setting_form');
    FF.ajax({
        url: '/gommi_download_manager/queue/command/setting_save',
        data: form_data,
        success: function(ret) {
            if (ret.ret === 'success') {
                notify.success('설정이 저장되었습니다.');
            } else {
                notify.danger(ret.msg || '저장 실패');
            }
        }
    });
}
